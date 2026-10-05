import json
import tempfile
import unittest
from pathlib import Path

from backend.wiki.archive import register_records, source_text, source_url


class ArchiveSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.docs=self.root/'documents'; self.groups=self.root/'groups'; self.wiki=self.root/'wiki'
        self.docs.mkdir();self.groups.mkdir()
        (self.docs/'chronicle_part_001.txt').write_text('Заголовок\nТочный архивный факт.\nКонец\n',encoding='utf-8')
        self.ref='archive:chronicle_part_001.txt:L2-L2'
        self.record={'post_id':self.ref,'source_kind':'archive','group_domain':'rso_tesla','post_url':source_url(self.ref), 'text_raw':'Точный архивный факт.', 'source_segments':[{'file':'chronicle_part_001.txt','line_start':2,'line_end':2}]}

    def test_exact_excerpt_and_named_viewer(self):
        self.assertEqual(register_records(self.wiki,[self.record],self.docs,self.groups),1)
        text=source_text(self.ref,self.wiki)
        self.assertIn('Точный архивный факт.',text)
        self.assertIn('chronicle_part_001.txt#L2-L2',text)
        self.assertIsNone(source_text('../.env',self.wiki))
        self.assertIsNone(source_text('archive:chronicle_part_001.txt:L1-L3',self.wiki))

    def test_text_mismatch_and_bad_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            register_records(self.wiki,[{**self.record,'text_raw':'Выдуманный факт'}],self.docs,self.groups)
        bad={**self.record,'source_segments':[{'file':'chronicle_part_001.txt','line_start':2,'line_end':999}]}
        with self.assertRaises(ValueError):register_records(self.wiki,[bad],self.docs,self.groups)
        with self.assertRaises(ValueError):
            register_records(self.wiki,[{**self.record,'group_domain':'spoyunost'}],self.docs,self.groups)

    def test_group_snapshot_keeps_unknown_publication_date(self):
        metadata={'domain':'rso_tesla','name':'Тесла','description':'Штаб'}
        (self.groups/'groups_rso_tesla.json').write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf-8')
        source={'post_id':'group:rso_tesla','source_kind':'group','group_domain':'rso_tesla','post_url':'https://vk.com/rso_tesla','text_raw':json.dumps(metadata,ensure_ascii=False,indent=2)}
        register_records(self.wiki,[source],self.docs,self.groups)
        record=json.loads((self.wiki/'_source_records.json').read_text())['group:rso_tesla']
        self.assertEqual(record['published_at'],'')
        self.assertIsNone(source_text('group:rso_tesla',self.wiki))


if __name__=='__main__':unittest.main()
