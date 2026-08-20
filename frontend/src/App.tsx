import React, { useState } from 'react'

import { Icon28MessageOutline, Icon28ServicesOutline } from '@vkontakte/icons'
import {
  AppRoot,
  Panel,
  PanelHeader,
  SplitCol,
  SplitLayout,
  Tabbar,
  TabbarItem,
  View,
} from '@vkontakte/vkui'

import { AuthProvider } from './auth/authContext'
import ChatPage from './pages/ChatPage'
import StatusPage from './pages/StatusPage'

type Screen = 'chat' | 'status'

function AppInner(): React.JSX.Element {
  const [screen, setScreen] = useState<Screen>('chat')

  return (
    <AppRoot>
      <SplitLayout style={{ maxWidth: 720, margin: '0 auto' }}>
        <SplitCol width="100%">
          <View activePanel={screen}>
            <Panel id="chat">
              <PanelHeader>Штаб Тесла — Чат</PanelHeader>
              <ChatPage />
            </Panel>
            <Panel id="status">
              <PanelHeader>Статус</PanelHeader>
              <StatusPage />
            </Panel>
          </View>
          <Tabbar>
            <TabbarItem
              selected={screen === 'chat'}
              onClick={() => setScreen('chat')}
              label="Чат"
            >
              <Icon28MessageOutline />
            </TabbarItem>
            <TabbarItem
              selected={screen === 'status'}
              onClick={() => setScreen('status')}
              label="Статус"
            >
              <Icon28ServicesOutline />
            </TabbarItem>
          </Tabbar>
        </SplitCol>
      </SplitLayout>
    </AppRoot>
  )
}

export default function App(): React.JSX.Element {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  )
}