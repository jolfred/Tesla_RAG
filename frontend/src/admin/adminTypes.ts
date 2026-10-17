export type AdminTab = 'overview' | 'materials' | 'sources' | 'tasks' | 'instructions'
export const ADMIN_TABS: {id:AdminTab;title:string;hint:string}[]=[
 {id:'overview',title:'Обзор',hint:'Новые материалы и следующие действия'},
 {id:'materials',title:'Материалы',hint:'Документы и входящие материалы'},
 {id:'sources',title:'Источники',hint:'Документы и VK-группы для сбора'},
 {id:'tasks',title:'Задачи',hint:'Сбор, расписание и результаты'},
 {id:'instructions',title:'Инструкции',hint:'Версии промптов и тест чата'},
]
