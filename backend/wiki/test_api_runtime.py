"""ASGI checks without external services or a real sessions database."""
import sys
import unittest
from unittest.mock import patch

import httpx
from backend.api.auth import verify_user_any, verify_admin_session, verify_admin_session_optional
from backend.main import app
from backend.wiki.loop import SILENCE, WikiUnavailable


class WikiApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.overrides = app.dependency_overrides.copy()
        app.dependency_overrides[verify_user_any] = lambda: 'user'
        app.dependency_overrides[verify_admin_session] = lambda: {'role':'admin'}
        app.dependency_overrides[verify_admin_session_optional] = lambda: None
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.overrides)

    async def test_empty_wiki_returns_silence_both_chats(self):
        with patch('backend.wiki.service.try_wiki_answer', return_value=None):
            for route in ('/api/v1/chat', '/api/v1/admin/chat'):
                response = await self.client.post(route, json={'question':'нет данных'})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['answer'], SILENCE)
                self.assertEqual(response.json()['sources'], [])

    async def test_provider_failure_is_503_both_chats(self):
        with patch('backend.wiki.service.try_wiki_answer', side_effect=WikiUnavailable('provider')):
            for route in ('/api/v1/chat', '/api/v1/admin/chat'):
                response = await self.client.post(route, json={'question':'вопрос'})
                self.assertEqual(response.status_code, 503, response.text)

    async def test_wiki_answer_and_admin_context(self):
        result = {'answer':'Факт [публикация](https://vk.com/wall-1_2)', 'pages':['yunost'], 'sources':[{'url':'https://vk.com/wall-1_2','title':'Назначение'}], 'calls':[{'name':'wiki_read','arguments':{'slug':'yunost'},'result':{'status':'success'}}]}
        with patch('backend.wiki.service.try_wiki_answer', return_value=result):
            response = await self.client.post('/api/v1/chat', json={'question':'вопрос','include_context':True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json()['calls'])
            app.dependency_overrides[verify_admin_session_optional] = lambda: {'role':'admin'}
            response = await self.client.post('/api/v1/chat', json={'question':'вопрос','include_context':True})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['calls'][0]['title'], 'wiki_read')

    async def test_status_and_legacy_route_removed(self):
        self.assertEqual((await self.client.get('/api/v1/status')).json()['mode'], 'wiki')
        self.assertEqual((await self.client.get('/api/v1/communities')).status_code,404)
        response=await self.client.post('/api/v1/admin/projects/test/index',json={})
        self.assertEqual(response.status_code,410)
        self.assertFalse(any(n.startswith(('backend.graph.','backend.embeddings.','backend.rag.')) for n in sys.modules))


if __name__ == '__main__':
    unittest.main()
