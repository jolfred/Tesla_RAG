"""Offline checks for the Wiki-only contract, including failure paths."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.wiki import loop
from backend.wiki.service import WikiAnswerService, WikiProjectUnavailable
from backend.wiki.test_loop import FakeClient, _fc


class WikiRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.joinpath("yunost.md").write_text('# СПО «Юность»\n\n## Командный состав\nКомандир 2024 [назначение](https://vk.com/wall-1_2)\n' + 'x' * 14000 + '\nКонец статьи', encoding='utf-8')
        self.root.joinpath("stub.md").write_text('---\nstatus: stub\n---\n# Пустая', encoding='utf-8')
        self.root.joinpath("_review").mkdir()
        self.root.joinpath("_review/private.md").write_text('# Секрет\nЮность командир 2024', encoding='utf-8')
        p = patch.object(loop, "WIKI_DIR", self.root)
        p.start(); self.addCleanup(p.stop)

    def test_full_article_and_continuation(self):
        first = loop.wiki_read("yunost")
        self.assertTrue(first["truncated"])
        self.assertEqual(first["next_offset"], loop.READ_LIMIT)
        continuation = loop.wiki_read("yunost", offset=first["next_offset"])
        self.assertEqual(continuation["markdown"], self.root.joinpath("yunost.md").read_text()[6000:12000])
        self.assertTrue(loop.wiki_read("yunost", full=True)["markdown"].endswith('Конец статьи'))
        self.assertEqual(loop.wiki_read("yunost", "несуществующий раздел")["status"], "fail")

    def test_private_stub_and_traversal(self):
        self.assertEqual(set(loop._pages()), {"yunost"})
        for slug in ("_review/private", "stub", "../yunost"):
            self.assertEqual(loop.wiki_read(slug)["status"], "fail")

    def test_symlink_outside_wiki_is_never_read(self):
        with tempfile.TemporaryDirectory() as other:
            outside=Path(other)/'outside.md'
            outside.write_text('# Юность\nСекретное содержимое',encoding='utf-8')
            self.root.joinpath('leak.md').symlink_to(outside)
            self.assertNotIn('leak', loop._pages())
            self.assertEqual(loop.wiki_read('leak')['status'],'fail')
            self.assertEqual(loop.wiki_search('секретное')['items'],[])

    def test_search_identity(self):
        self.root.joinpath("mentions.md").write_text('# Дайнима\n## История\n' + 'Юность командир 2024 ' * 300, encoding='utf-8')
        self.assertEqual(loop.wiki_search('Юности командиры 2024', 1)['items'][0]['slug'], 'yunost')

    def test_no_ungrounded_answer(self):
        client = FakeClient([{"message": {"content": "Выдуманный факт"}, "finish_reason": "stop"}])
        self.assertIsNone(loop.try_wiki_answer('вопрос', client=client))

    def test_citations_must_be_in_read_fragment(self):
        client = FakeClient([_fc('wiki_read', {'slug':'yunost'}), {"message":{"content":"Факт [источник](https://evil.example/wall-1_2)"}, "finish_reason":"stop"}])
        self.assertIsNone(loop.try_wiki_answer('вопрос', client=client))

    def test_uncited_paragraph_and_internal_link_require_revision(self):
        client=FakeClient([_fc('wiki_read', {'slug':'yunost'}),
            {'message':{'content':'Факт без источника.\n\n[назначение](https://vk.com/wall-1_2) [[yunost]]'},'finish_reason':'stop'},
            {'message':{'content':'Командир упомянут в 2024 году. [wall-1_2](https://vk.com/wall-1_2)'},'finish_reason':'stop'}])
        result=loop.try_wiki_answer('вопрос',client=client,raise_on_error=True)
        self.assertEqual(client.calls,3)
        self.assertNotIn('[[',result['answer'])
        self.assertNotIn('[wall-1_2]',result['answer'])
        self.assertIn('https://vk.com/wall-1_2',result['answer'])

    def test_strict_provider_failure(self):
        class Broken:
            def chat_with_functions(self, *args, **kwargs):
                raise RuntimeError('offline')
        with self.assertRaises(loop.WikiUnavailable):
            loop.try_wiki_answer('вопрос', client=Broken(), raise_on_error=True)

    def test_malformed_provider_response_is_unavailable(self):
        for response in (None, {}, {"message": []}, {"message": {"content": []}},
                         {"message": {"function_call": "broken"}}):
            with self.subTest(response=response):
                with self.assertRaises(loop.WikiUnavailable):
                    loop.try_wiki_answer('вопрос', client=FakeClient([response]), raise_on_error=True)

    def test_service_absence_error_and_project(self):
        with patch('backend.wiki.service.try_wiki_answer', return_value=None):
            self.assertEqual(WikiAnswerService().search('вопрос')['answer'], loop.SILENCE)
        with patch('backend.wiki.service.try_wiki_answer', side_effect=loop.WikiUnavailable('provider')):
            with self.assertRaises(loop.WikiUnavailable):
                WikiAnswerService().search('вопрос')
        with patch('backend.wiki.service.try_wiki_answer') as call:
            with self.assertRaises(WikiProjectUnavailable):
                WikiAnswerService().search('вопрос', project_slug='test')
            call.assert_not_called()

    def test_canon_is_verbatim(self):
        from backend.wiki.prompts import query_prompt, SCHEMA_DIR
        prompt = query_prompt()
        for name in ('rules.md','rules_mapping.md'):
            self.assertIn((SCHEMA_DIR/name).read_text(encoding='utf-8'), prompt)

    def test_status_does_not_probe_network(self):
        from backend.api.routes.status import status
        result = status()
        self.assertEqual(result.mode, 'wiki')
        self.assertEqual(result.wiki_pages, 1)
        self.assertFalse(result.errors)


if __name__ == '__main__':
    unittest.main()
