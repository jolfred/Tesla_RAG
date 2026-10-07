import json
import hashlib
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path

from backend.wiki.ingest import inventory, export_posts, import_results, apply, connect, retrieval_pack, stage_proposals, apply_proposals, identity, relevant_page_catalog, verify_posts
from backend.wiki.ingest_runner import call_provider, _codex_eligible, compile_wiki, _json_object


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name); self.db = self.root / 'ledger.sqlite'
        self.posts = self.root / 'posts.jsonl'
        self.post = {'post_id':'wall-12_34','group_domain':'spoyunost2020','published_at':'2024-02-01T00:00:00Z',
                     'text_raw':'В 2024 году командиром стал Иван.','text_clean':'В 2024 году командиром стал Иван.'}
        self.posts.write_text(json.dumps(self.post,ensure_ascii=False)+'\n',encoding='utf-8')
        self.wiki = self.root / 'wiki'; (self.wiki/'lso').mkdir(parents=True)
        (self.wiki/'lso/yunost.md').write_text('---\ntitle: Юность\n---\n\n# Юность\n\n## История\n\n## Контакты\n',encoding='utf-8')
        inventory(self.db,self.posts)
        self.source_hash=hashlib.sha256(self.post['text_raw'].encode()).hexdigest()

    def tearDown(self): self.tmp.cleanup()

    def test_invalid_quote_goes_to_review_and_refusal_is_not_noise(self):
        handoff=self.root/'h.json'
        handoff.write_text(json.dumps({'posts':[
            {'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[{'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high','joke_flag':False,'role_scope':None,'status':'verified','date_event':None,'facts':[{'detail':'Несуществующее событие','quote':'нет такой цитаты'}]}]},
            {'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'refused','reason':'provider refusal'}]},ensure_ascii=False),encoding='utf-8')
        import_results(self.db,handoff)
        con=connect(self.db)
        self.assertEqual(con.execute('select state from facts').fetchone()[0],'review')
        self.assertEqual(con.execute('select state from posts').fetchone()[0],'review')
        con.close()

    def test_impossible_calendar_date_and_undated_role_require_review(self):
        from backend.wiki.ingest import _date_ok,validate_post_result
        self.assertTrue(_date_ok('2024-02-29'))
        for value in ('2023-02-29','2024-13','2024-01-32',2024):self.assertFalse(_date_ok(value))
        role={'class':'role','page_slug':'lso/yunost','section':'## История','confidence':'high',
              'joke_flag':False,'role_scope':'squad','status':'verified','date_event':None,
              'facts':[{'detail':'Иван назван командиром.','quote':'командиром стал Иван'}]}
        result={'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[role]}
        validated=validate_post_result(result,{('wall-12_34',self.source_hash):self.post['text_raw']})
        self.assertEqual(validated[0][1],'role time period is not confirmed')

    def test_apply_is_source_marked_idempotent_and_keeps_undated_fact(self):
        handoff=self.root/'h.json'
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high','joke_flag':False,'role_scope':None,'status':'verified','date_event':None,'facts':[{'detail':'Иван назван командиром отряда.','quote':'командиром стал Иван'}]}
        handoff.write_text(json.dumps({'posts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[item]}]},ensure_ascii=False),encoding='utf-8')
        import_results(self.db,handoff)
        self.assertEqual(apply(self.db,self.wiki)['applied'],1)
        self.assertEqual(apply(self.db,self.wiki)['applied'],0)
        text=(self.wiki/'lso/yunost.md').read_text()
        self.assertIn('Иван назван командиром',text); self.assertNotIn('дата не указана',text)

    def test_stable_hash_and_export_limit(self):
        self.assertEqual(inventory(self.db,self.posts)['new_versions'],0)
        with self.assertRaises(ValueError): export_posts(self.db,51)

    def test_only_one_compiler_can_write_a_ledger(self):
        import fcntl
        with self.db.with_suffix('.sqlite.compile.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError,'another compiler'):
                compile_wiki(self.db,self.wiki,self.root/'run',self.root/'extract.md',self.root/'merge.md')

    def test_broken_outer_json_cannot_be_replaced_with_a_complete_child(self):
        with self.assertRaises(ValueError):
            _json_object('{"posts":[{"post_id":"wall-12_34"}')
        self.assertEqual(_json_object('```json\n{"posts":[]}\n```'), {'posts': []})

    def test_specific_person_beats_large_general_registry(self):
        people=self.wiki/'persons';people.mkdir()
        (people/'ivan.md').write_text('# Иван Иванов\n\n## Должности\n',encoding='utf-8')
        (people/'index.md').write_text('# Реестр персон\n\n## Командиры\n'+('Иван Иванов командир 2024 история Юность\n'*500),encoding='utf-8')
        pages=relevant_page_catalog(self.wiki,'В 2024 году командир Иван Иванов выступил.',1)
        self.assertEqual(pages[0]['page_slug'],'persons/ivan')

    def test_archive_url_with_encoded_id_is_a_valid_citation(self):
        from backend.wiki.archive import source_url
        pid='archive:chronicle_part_039.txt:L172-L174';raw='Точный архивный факт.'
        source={'post_id':pid,'source_kind':'archive','post_url':source_url(pid),'text_raw':raw,
                'archive_source_uri':'storage/documents/chronicle_part_039.txt#L172',
                'source_segments':[{'file':'chronicle_part_039.txt','line_start':172,'line_end':174}]}
        inputs=self.root/'archive.jsonl';inputs.write_text(json.dumps(source)+'\n')
        inventory(self.db,inputs);sha=hashlib.sha256(raw.encode()).hexdigest()
        extract=self.root/'extract-archive.json'
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high',
              'joke_flag':False,'role_scope':None,'status':'verified','date_event':None,'facts':[{'detail':raw,'quote':raw}]}
        extract.write_text(json.dumps({'posts':[{'post_id':pid,'source_hash':sha,'outcome':'extracted','items':[item]}]}))
        import_results(self.db,extract)
        old=(self.wiki/'lso/yunost.md').read_text()
        prop={'page_slug':'lso/yunost','expected_sha256':hashlib.sha256(old.encode()).hexdigest(),'new_page':False,
              'source_post_ids':[pid,pid],'source_refs':[{'post_id':pid,'source_hash':sha},{'post_id':pid,'source_hash':sha}],
              'covered_facts':[{'post_id':pid,'source_hash':sha,'ordinal':0}],'markdown':None,
              'patches':[{'old_text':'','new_text':raw+' (Источник: [Архивная публикация]('+source_url(pid)+')).'}]}
        merge=self.root/'merge-archive.json';merge.write_text(json.dumps({'pages':[prop]}))
        self.assertEqual(stage_proposals(self.db,self.wiki,merge),{'staged':1,'review':0})
        self.assertEqual(apply_proposals(self.db,self.wiki)['applied_pages'],1)

    def test_exact_patches_preserve_legacy_article_without_frontmatter(self):
        target=self.wiki/'lso/yunost.md';old='# Юность\n\n## История\n\nСуществующая история отряда.\n'
        target.write_text(old)
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high','joke_flag':False,
              'role_scope':None,'status':'verified','date_event':None,'facts':[{'detail':'Иван стал командиром.','quote':'командиром стал Иван'}]}
        handoff=self.root/'extract.json';handoff.write_text(json.dumps({'posts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[item]}]}))
        import_results(self.db,handoff)
        prop={'page_slug':'lso/yunost','expected_sha256':hashlib.sha256(old.encode()).hexdigest(),'new_page':False,
              'source_post_ids':['wall-12_34'],'source_refs':[{'post_id':'wall-12_34','source_hash':self.source_hash}],
              'covered_facts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'ordinal':0}], 'markdown':None,
              'patches':[{'old_text':'Несуществующая строка','new_text':'Плохая правка'}]}
        merge=self.root/'merge.json';merge.write_text(json.dumps({'pages':[prop]}))
        with self.assertRaises(ValueError):stage_proposals(self.db,self.wiki,merge)
        self.assertEqual(target.read_text(),old)
        prop['patches']=[{'old_text':'','new_text':'Иван стал командиром. (Источник: [wall-12_34](https://vk.com/wall-12_34))'}]
        merge.write_text(json.dumps({'pages':[prop]}))
        self.assertEqual(stage_proposals(self.db,self.wiki,merge),{'staged':1,'review':0})
        self.assertEqual(apply_proposals(self.db,self.wiki)['applied_pages'],1)
        self.assertIn('Существующая история отряда.',target.read_text())

    def test_insert_after_preserves_the_exact_old_cited_line(self):
        from backend.wiki.ingest_runner import _output_schema
        target=self.wiki/'lso/yunost.md'
        anchor='- Старая история. (Источник: [старый пост](https://vk.com/wall-12_10)).'
        old=target.read_text()+'\n'+anchor+'\n';target.write_text(old)
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high',
              'joke_flag':False,'status':'verified','date_event':None,
              'facts':[{'detail':'Иван назван командиром.','quote':'командиром стал Иван'}]}
        handoff=self.root/'extract.json'
        handoff.write_text(json.dumps({'posts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[item]}]}))
        import_results(self.db,handoff)
        addition='- Иван назван командиром. (Источник: [wall-12_34](https://vk.com/wall-12_34)).'
        prop={'page_slug':'lso/yunost','expected_sha256':hashlib.sha256(old.encode()).hexdigest(),'new_page':False,
              'source_post_ids':['wall-12_34'],'source_refs':[{'post_id':'wall-12_34','source_hash':self.source_hash}],
              'covered_facts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'ordinal':0}],
              'markdown':None,'patches':[{'operation':'insert_after','old_text':anchor,'new_text':addition}]}
        merge=self.root/'merge.json';merge.write_text(json.dumps({'pages':[prop]}))
        self.assertEqual(stage_proposals(self.db,self.wiki,merge,insertion_only=True),{'staged':1,'review':0})
        self.assertEqual(apply_proposals(self.db,self.wiki)['applied_pages'],1)
        self.assertEqual(target.read_text().count(anchor),1)
        self.assertIn(anchor+'\n'+addition,target.read_text())
        operation=_output_schema('merge')['properties']['pages']['items']['properties']['patches']['items']['properties']['operation']
        self.assertEqual(operation['enum'],['insert_after'])

    def test_routine_merge_rejects_legacy_replacement_patch(self):
        target=self.wiki/'lso/yunost.md'
        prop={'page_slug':'lso/yunost','new_page':False,'markdown':None,
              'patches':[{'old_text':'## История','new_text':'## Новая история'}]}
        handoff=self.root/'merge.json';handoff.write_text(json.dumps({'pages':[prop]}))
        with self.assertRaisesRegex(ValueError,'requires insert_after'):
            stage_proposals(self.db,self.wiki,handoff,insertion_only=True)
        self.assertIn('## История',target.read_text())

    def test_shortened_full_article_is_sent_to_review(self):
        target=self.wiki/'lso/yunost.md';old=target.read_text()+'\n'+'Старая история отряда.\n'*100
        target.write_text(old)
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high','joke_flag':False,
              'role_scope':None,'status':'verified','date_event':None,'facts':[{'detail':'Иван стал командиром.','quote':'командиром стал Иван'}]}
        h=self.root/'extract.json';h.write_text(json.dumps({'posts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[item]}]}))
        import_results(self.db,h)
        p={'page_slug':'lso/yunost','expected_sha256':hashlib.sha256(old.encode()).hexdigest(),'new_page':False,
           'source_post_ids':['wall-12_34'],'source_refs':[{'post_id':'wall-12_34','source_hash':self.source_hash}],
           'covered_facts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'ordinal':0}],
           'markdown':'# Юность\n\nИван стал командиром. [wall-12_34](https://vk.com/wall-12_34)\n'}
        m=self.root/'merge.json';m.write_text(json.dumps({'pages':[p]}))
        self.assertEqual(stage_proposals(self.db,self.wiki,m),{'staged':0,'review':1})
        self.assertEqual(target.read_text(),old)

    def test_empty_raw_is_persisted_as_skipped_and_oversize_source_is_whole(self):
        empty=self.root/'empty.jsonl'
        empty.write_text(json.dumps({'post_id':'wall-12_35','text_raw':''})+'\n',encoding='utf-8')
        inventory(self.db,empty)
        rows=connect(self.db).execute("select state,reason from posts where post_id='wall-12_35'").fetchone()
        self.assertEqual(tuple(rows),('skipped','empty raw source text'))
        huge='А'*40001
        pfile=self.root/'huge.jsonl'; pfile.write_text(json.dumps({'post_id':'wall-12_36','text_raw':huge})+'\n',encoding='utf-8')
        inventory(self.db,pfile)
        con=connect(self.db); con.execute("update posts set state='applied' where post_id!='wall-12_36'"); con.commit(); con.close()
        posts=export_posts(self.db,50,max_chars=40000)
        self.assertEqual(len(posts),1); self.assertEqual(posts[0]['text_raw'],huge)

    def test_valid_new_page_is_staged_then_created_atomically(self):
        extract=self.root/'extract.json'
        item={'class':'role','page_slug':'persons/ivan','section':'## Роли','confidence':'high','joke_flag':False,
              'role_scope':'squad','status':'verified','date_event':'2024','facts':[{'detail':'Иван упомянут командиром.','quote':'командиром стал Иван'}]}
        extract.write_text(json.dumps({'posts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':[item]}]},ensure_ascii=False),encoding='utf-8')
        import_results(self.db,extract)
        merge=self.root/'merge.json'
        content='---\nslug: persons/ivan\nkind: person\nstatus: verified\ntitle: Иван\ntags: [персона]\n---\n\n# Иван\n\n## Роли\n\nВ 2024 году назван командиром. (Источник: [wall-12_34](https://vk.com/wall-12_34))\n'
        merge.write_text(json.dumps({'pages':[{'page_slug':'persons/ivan','new_page':True,'expected_sha256':None,'source_post_ids':['wall-12_34'],'source_refs':[{'post_id':'wall-12_34','source_hash':self.source_hash}],'covered_facts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'ordinal':0}],'markdown':content}]},ensure_ascii=False),encoding='utf-8')
        self.assertEqual(stage_proposals(self.db,self.wiki,merge),{'staged':1,'review':0})
        self.assertEqual(apply_proposals(self.db,self.wiki)['applied_pages'],1)
        self.assertTrue((self.wiki/'persons/ivan.md').is_file())

    def test_numeric_vk_id_normalization_and_untrusted_host_rejection(self):
        post={'post_id':'5096','group_id':'198864697','post_url':'https://vk.com/spoyunost2020?w=wall-198864697_5096','text_raw':'факт'}
        self.assertEqual(identity(post)[0],'wall-198864697_5096')
        with self.assertRaises(ValueError): identity({**post,'post_url':'https://evil.example/?w=wall-198864697_5096'})
        with self.assertRaises(ValueError): identity({**post,'post_id':'wall--198864697_5096'})

    def test_typed_archive_and_group_ids_preserve_exact_provenance_without_fabricated_wall_ids(self):
        archive_id='archive:chronicle_part_039.txt:L172-L174'
        archive={'source_kind':'archive','post_id':archive_id,'post_url':'/api/v1/wiki/source?ref=archive%3Achronicle_part_039.txt%3AL172-L174',
            'archive_source_uri':'storage/documents/chronicle_part_039.txt#L172','source_segments':[{'file':'chronicle_part_039.txt','line_start':172,'line_end':174}],
            'text_raw':'Exact archived text'}
        self.assertEqual(identity(archive)[0],archive_id)
        with self.assertRaises(ValueError): identity({**archive,'post_url':'https://vk.com/wall-39_172'})
        group={'source_kind':'group','post_id':'group:dainima','group_domain':'dainima','post_url':'https://vk.com/dainima',
            'published_at':None,'text_raw':'Group metadata snapshot'}
        self.assertEqual(identity(group)[0],'group:dainima')
        with self.assertRaises(ValueError): identity({**group,'published_at':'2026-10-05'})
        rendered=__import__('backend.wiki.ingest',fromlist=['_render'])._render(archive_id,
            {'date_event':None,'facts':[{'detail':'Событие из хроники.','quote':'Exact archived text'}]},archive['post_url'])
        self.assertIn(archive['post_url'],rendered)
        self.assertNotIn('vk.com/wall',rendered)

    def test_archive_segments_and_cli_verify_split_typed_id_at_trailing_hash(self):
        from scripts.wiki_ingest import parse_verify_pair
        raw='--- archive fixture ---'
        pid='archive:chronicle_part_039.txt:L172-L174'
        p={'source_kind':'archive','post_id':pid,'post_url':'/api/v1/wiki/source?ref=archive%3Achronicle_part_039.txt%3AL172-L174',
           'archive_source_uri':'storage/documents/chronicle_part_039.txt#L172','source_segments':[{'file':'chronicle_part_039.txt','line_start':172,'line_end':174}],
           'text_raw':raw}
        f=self.root/'archive.jsonl'; f.write_text(json.dumps(p)+'\n',encoding='utf-8')
        inventory(self.db,f)
        digest=hashlib.sha256(raw.encode()).hexdigest()
        handoff=self.root/'archive-extract.json'
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high','joke_flag':False,
            'role_scope':None,'status':'verified','date_event':None,'facts':[{'detail':'Событие из архива.','quote':'Exact archived text'}]}
        handoff.write_text(json.dumps({'posts':[{'post_id':pid,'source_hash':digest,'outcome':'extracted','items':[item]}]}),encoding='utf-8')
        import_results(self.db,handoff)
        self.assertEqual(verify_posts(self.db,[(pid,digest)]),1)
        self.assertEqual(parse_verify_pair(pid+":"+digest),(pid,digest))

    def test_catalog_contains_only_compact_page_metadata(self):
        catalog=relevant_page_catalog(self.wiki,'Юность командир',5)
        self.assertLessEqual(len(catalog),5)
        self.assertTrue(all(set(x)=={'page_slug','title','headings'} for x in catalog))

    def test_catalog_excludes_level_three_sections_from_extraction_hints(self):
        page=self.wiki/'lso/yunost.md'
        page.write_text(page.read_text()+'\n### Командиры\n',encoding='utf-8')
        catalog=relevant_page_catalog(self.wiki,'Юность командир',5)
        self.assertTrue(catalog)
        self.assertTrue(all(h.startswith('## ') for entry in catalog for h in entry['headings']))

    def test_future_placement_cannot_be_imported_as_verified(self):
        from backend.wiki.ingest import validate_post_result
        raw='В этом году отряд проведет третий трудовой семестр в лагере.'
        sha=hashlib.sha256(raw.encode()).hexdigest()
        item={'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high',
              'joke_flag':False,'status':'verified','date_event':'2023',
              'facts':[{'detail':raw,'quote':raw}]}
        result={'post_id':'wall-12_34','source_hash':sha,'outcome':'extracted','items':[item]}
        known={('wall-12_34',sha):raw}
        self.assertIn('future event',validate_post_result(result,known)[0][1])
        item['status']='planned'
        self.assertIsNone(validate_post_result(result,known)[0][1])

    def test_codex_model_effort_and_machine_usage_are_forwarded(self):
        root=Path(__file__).resolve().parents[2]
        prompt=root/'schema/prompts/wiki_extract_en.md'
        bundle=self.root/'bundle.json'; bundle.write_text('{"posts":[]}',encoding='utf-8')
        for model in ('gpt-6-luna','gpt-5.6-luna'):
            for effort in ('low','medium'):
                out=self.root/f'{model}-{effort}.json'
                def fake_run(cmd, **kwargs):
                    Path(cmd[cmd.index('-o')+1]).write_text('{"posts":[]}',encoding='utf-8')
                    return SimpleNamespace(returncode=0,stdout='',stderr='')
                with patch('backend.wiki.ingest_runner._codex_eligible',return_value=True) as guard, \
                     patch('backend.wiki.ingest_runner.subprocess.run',side_effect=fake_run) as run:
                    self.assertEqual(call_provider('codex',effort,prompt,bundle,out,self.root/'work',model),{'posts':[]})
                guard.assert_called_once()
                cmd=run.call_args.args[0]
                self.assertEqual(cmd[cmd.index('-m')+1],model)
                self.assertIn(f'model_reasoning_effort="{effort}"',cmd)
                self.assertIn('--json',cmd)

    def test_direct_codex_call_stops_when_quota_is_unavailable(self):
        root=Path(__file__).resolve().parents[2]
        with patch('backend.wiki.ingest_runner._codex_eligible',return_value=False), \
             patch('backend.wiki.ingest_runner.subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError,'actual quota guard'):
                call_provider('codex','low',root/'schema/prompts/wiki_extract_en.md',
                              self.root/'bundle.json',self.root/'out.json',self.root/'work')
        run.assert_not_called()

    def test_opencode_call_has_prompt_and_bundle_attachments_and_readonly_agent(self):
        root=Path(__file__).resolve().parents[2]
        prompt=root/'schema/prompts/wiki_extract_en.md'; bundle=self.root/'bundle.json'; bundle.write_text('{"posts":[]}',encoding='utf-8')
        out=self.root/'result.json'; event=json.dumps({'type':'text','part':{'text':'{"ok":true}'}})
        with patch('backend.wiki.ingest_runner.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=event+'\n',stderr='')) as run:
            self.assertEqual(call_provider('opencode','low',prompt,bundle,out,self.root/'llm-work','opencode/mimo-v2.6-flash-free'),{'ok':True})
        cmd=run.call_args.args[0]
        client = cmd.index('/app/opencode', cmd.index('--chdir'))
        self.assertEqual(cmd[client:client+2],['/app/opencode','run'])
        self.assertTrue(cmd[client+2].startswith('Follow the attached system prompt'))
        self.assertNotIn('--variant', cmd)

        self.assertLess(client+2,cmd.index('--file'))
        self.assertIn('--agent',cmd); self.assertIn('plan',cmd)
        file_args=[cmd[i+1] for i,x in enumerate(cmd[:-1]) if x=='--file']
        self.assertEqual({Path(p).name for p in file_args},{'stage-instructions.md','input-bundle.json'})
        self.assertEqual(len(file_args),2)
        self.assertTrue(all(str(p).startswith('/work/') for p in file_args))
        self.assertIn('--clearenv',cmd); self.assertIn('--unshare-pid',cmd)
        self.assertNotIn('--auto',cmd)

    def test_longcat_effort_is_forwarded_to_cli(self):
        from backend.wiki.cli_isolation import opencode_command
        for effort in ('low','medium'):
            cmd=opencode_command(self.root,'opencode/longcat-2.5-preview-free','plan',effort)
            self.assertEqual(cmd[cmd.index('--variant')+1],effort)
            config=json.loads((self.root/'opencode.json').read_text())
            self.assertEqual(config['provider']['opencode']['models']['longcat-2.5-preview-free']['options']['thinking']['type'],'disabled')

    def test_longcat_rejects_unknown_effort(self):
        from backend.wiki.cli_isolation import opencode_command
        with self.assertRaises(ValueError):
            opencode_command(self.root,'opencode/longcat-2.5-preview-free','plan','invalid')

    def test_worker_and_cli_try_verified_free_mimo_first(self):
        import inspect
        from scripts.wiki_ingest import DEFAULT_EXTRACT, DEFAULT_MERGE, FREE_FALLBACKS
        params=inspect.signature(compile_wiki).parameters
        self.assertEqual(DEFAULT_EXTRACT,'opencode/mimo-v2.6-flash-free')
        self.assertEqual(DEFAULT_MERGE,DEFAULT_EXTRACT)
        self.assertEqual(params['extract_model'].default,DEFAULT_EXTRACT)
        self.assertEqual(params['merge_model'].default,DEFAULT_MERGE)
        self.assertEqual(list(params['extract_fallback_models'].default),FREE_FALLBACKS)
        self.assertNotIn(DEFAULT_EXTRACT,FREE_FALLBACKS)

    def test_free_fallback_models_are_not_retried_when_duplicated(self):
        from backend.wiki.ingest_runner import call_provider_resilient
        model='opencode/longcat-2.5-preview-free'
        with patch('backend.wiki.ingest_runner.call_provider',side_effect=RuntimeError('unavailable')) as provider:
            with self.assertRaises(RuntimeError):
                call_provider_resilient('low',self.root/'prompt',self.root/'bundle',self.root/'out.json',
                                        self.root/'work',(model,model),False,'plan',self.root/'run')
        self.assertEqual(provider.call_count,1)

    def test_quota_fallback_uses_both_actual_windows_and_strict_ten_percent_reserve(self):
        with patch('backend.wiki.ingest_runner.read_codex_limits',return_value={'primary_used_percent':90,'secondary_used_percent':20}):
            self.assertFalse(_codex_eligible(self.root/'quota'))
        with patch('backend.wiki.ingest_runner.read_codex_limits',return_value={'primary_used_percent':89,'secondary_used_percent':20}):
            self.assertTrue(_codex_eligible(self.root/'quota'))

    def test_merge_applies_only_the_covered_fact_not_other_page_facts(self):
        extract=self.root/'extract-multi.json'
        base={'confidence':'high','joke_flag':False,'role_scope':None,'status':'verified','date_event':'2024'}
        items=[{**base,'class':'event','page_slug':'lso/yunost','section':'## История','facts':[{'detail':'Иван стал командиром.','quote':'командиром стал Иван'}]},
               {**base,'class':'role','role_scope':'squad','page_slug':'persons/ivan','section':'## Роли','facts':[{'detail':'Иван назван командиром.','quote':'командиром стал Иван'}]}]
        extract.write_text(json.dumps({'posts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'outcome':'extracted','items':items}]},ensure_ascii=False),encoding='utf-8')
        import_results(self.db,extract)
        old=(self.wiki/'lso/yunost.md').read_text(); digest=hashlib.sha256(old.encode()).hexdigest()
        merged=old.replace('## История','## История\n\nИван стал командиром (Источник: [wall-12_34](https://vk.com/wall-12_34)).')
        proposal=self.root/'merge-one.json'
        proposal.write_text(json.dumps({'pages':[{'page_slug':'lso/yunost','expected_sha256':digest,'new_page':False,
            'source_post_ids':['wall-12_34'],'source_refs':[{'post_id':'wall-12_34','source_hash':self.source_hash}],
            'covered_facts':[{'post_id':'wall-12_34','source_hash':self.source_hash,'ordinal':0}],'markdown':merged}]},ensure_ascii=False),encoding='utf-8')
        self.assertEqual(stage_proposals(self.db,self.wiki,proposal),{'staged':1,'review':0})
        self.assertEqual(apply_proposals(self.db,self.wiki)['applied_pages'],1)
        con=connect(self.db)
        states=[r[0] for r in con.execute('select state from facts order by ordinal')]
        post_state=con.execute('select state from posts').fetchone()[0]; con.close()
        self.assertEqual(states,['applied','extracted']); self.assertEqual(post_state,'extracted')

    def test_runner_persists_extract_then_stages_grounded_page_proposal_offline(self):
        import backend.wiki.ingest_runner as runner
        def fake_provider(effort, prompt, bundle_path, output_path, workdir, models, codex, agent, run_dir, validator=None):
            bundle=json.loads(bundle_path.read_text(encoding='utf-8'))
            if effort == 'low':
                post=bundle['posts'][0]
                result={'posts':[{'post_id':post['post_id'],'source_hash':post['source_hash'],'outcome':'extracted',
                    'items':[{'class':'event','page_slug':'lso/yunost','section':'## История','confidence':'high',
                    'joke_flag':False,'role_scope':None,'status':'verified','date_event':None,
                    'facts':[{'detail':'Иван назван командиром.','quote':'командиром стал Иван'}]}]}]}
            else:
                fact=bundle['candidate_facts']['lso/yunost'][0]
                old=(self.wiki/'lso/yunost.md').read_text(encoding='utf-8')
                source='https://vk.com/wall-12_34'
                addition='- Иван назван командиром. (Источник: [wall-12_34]('+source+')).\n'
                result={'pages':[{'page_slug':'lso/yunost','expected_sha256':hashlib.sha256(old.encode()).hexdigest(),
                    'new_page':False,'source_post_ids':['wall-12_34'],
                    'source_refs':[{'post_id':'wall-12_34','source_hash':fact['source_hash']}],
                    'covered_facts':[{'post_id':'wall-12_34','source_hash':fact['source_hash'],'ordinal':fact['fact_ordinal']}],
                    'markdown':None,'patches':[{'operation':'insert_after','old_text':'## История','new_text':addition}]}]}
            if validator is not None:
                validator(result)
            runner._atomic_json(output_path,result)
            return result
        root=Path(__file__).resolve().parents[2]
        with patch('backend.wiki.ingest_runner.call_provider_resilient',side_effect=fake_provider):
            result=compile_wiki(self.db,self.wiki,self.root/'run',root/'schema/prompts/wiki_extract_en.md',
                root/'schema/prompts/wiki_merge_en.md',max_posts=1,batch_size=1,do_apply=False)
        self.assertEqual(result['batches'],1); self.assertEqual(result['merge_calls'],1)
        proposal=connect(self.db).execute("select state,fact_refs from proposals where page_slug='lso/yunost'").fetchone()
        self.assertEqual(proposal['state'],'staged')
        self.assertEqual(json.loads(proposal['fact_refs']),[{'post_id':'wall-12_34','source_hash':self.source_hash,'ordinal':0}])


if __name__ == '__main__': unittest.main()
