import alteraLogo from '../assets/logos/altera.jpg'
import dainimaLogo from '../assets/logos/dainima.jpg'
import darLogo from '../assets/logos/dar.jpg'
import deltaLogo from '../assets/logos/delta.jpg'
import elementLogo from '../assets/logos/element.jpg'
import isidaLogo from '../assets/logos/isida.jpg'
import kgeuLogo from '../assets/logos/kgeu.jpg'
import monolitLogo from '../assets/logos/monolit.jpg'
import oniksLogo from '../assets/logos/oniks.jpg'
import teslaLogo from '../assets/logos/tesla.jpg'
import trudLogo from '../assets/logos/trud.jpg'
import trudKrutLogo from '../assets/logos/trud-krut.jpg'

export { kgeuLogo, trudLogo, trudKrutLogo }

export interface Squad {
  name: string
  short: string
  tag: string
  direction: string
  vk: string
  emblem: string
  /** Настоящий логотип отряда (ресайз 512px). Нет — показываем emblem. */
  logo?: string
}

export const SQUADS: Squad[] = [
  { name: 'ССО «Исида»', short: 'Исида', tag: 'стройка', direction: 'Строительное', vk: 'https://vk.ru/sso_isida', emblem: '◭', logo: isidaLogo },
  { name: 'ССО «Монолит»', short: 'Монолит', tag: 'стройка', direction: 'Строительное', vk: 'https://vk.ru/ssomonolitkazan', emblem: '⬢', logo: monolitLogo },
  { name: 'ССО «Высокое Напряжение»', short: 'Высокое Напряжение', tag: 'стройка × энерго', direction: 'Строительное', vk: 'https://vk.ru/sso_vysokoe_napryazhenie', emblem: '⚡' },
  { name: 'СПО «Дельта»', short: 'Дельта', tag: 'дети', direction: 'Педагогическое', vk: 'https://vk.ru/spodelta', emblem: '△', logo: deltaLogo },
  { name: 'СПО «Юность»', short: 'Юность', tag: 'дети', direction: 'Педагогическое', vk: 'https://vk.ru/spoyunost2020', emblem: '◍' },
  { name: 'СПО «ДАР»', short: 'ДАР', tag: 'дети', direction: 'Педагогическое', vk: 'https://vk.ru/spodar_16', emblem: '✦', logo: darLogo },
  { name: 'СОП «Energy»', short: 'Energy', tag: 'поезда', direction: 'Проводники', vk: 'https://vk.ru/sopenergy', emblem: '➤' },
  { name: 'ССервО «Оникс»', short: 'Оникс', tag: 'сервис', direction: 'Сервисное', vk: 'https://vk.ru/sservoonyx', emblem: '⬣', logo: oniksLogo },
  { name: 'ССервО «Альтера»', short: 'Альтера', tag: 'сервис', direction: 'Сервисное', vk: 'https://vk.ru/sservo_altera', emblem: '⬔', logo: alteraLogo },
  { name: 'СЭО «Заряд»', short: 'Заряд', tag: 'энерго', direction: 'Энергетическое', vk: 'https://vk.ru/seo_zaryad', emblem: 'ϟ' },
  { name: 'СЭО «Высокое Напряжение»', short: 'ВН', tag: 'энерго', direction: 'Энергетическое', vk: 'https://vk.ru/seo_vysokoe_napryazhenie', emblem: '⌁' },
  { name: 'СПроО «Элемент»', short: 'Элемент', tag: 'завод', direction: 'Производственное', vk: 'https://vk.ru/spro_element', emblem: '⬡', logo: elementLogo },
  { name: 'ОСД «Резонанс»', short: 'Резонанс', tag: 'десант', direction: 'Снежный десант', vk: 'https://vk.ru/osd_rezonans', emblem: '❄' },
  { name: 'ОСД «Сириус»', short: 'Сириус', tag: 'десант', direction: 'Снежный десант', vk: 'https://vk.ru/osd_sirius21', emblem: '✧' },
  { name: 'ШКБ «Погружение»', short: 'Погружение', tag: 'школа', direction: 'Школа бойцов', vk: 'https://vk.ru/shkb_pogruzhenie', emblem: '▼' },
  { name: 'ССО «Дайнима»', short: 'Дайнима', tag: 'стройка', direction: 'Строительное', vk: 'https://vk.ru/dainima', emblem: '◆', logo: dainimaLogo },
  { name: 'ПрогрессLAB', short: 'ПрогрессLAB', tag: 'медиа × tech', direction: 'Проектный центр', vk: 'https://vk.ru/club225166105', emblem: '◈' },
  { name: 'Штаб «Тесла»', short: 'Тесла', tag: 'штаб', direction: 'Головной штаб', vk: 'https://vk.ru/rso_tesla', emblem: '⟡', logo: teslaLogo },
]

export interface Direction {
  code: string
  title: string
  desc: string
  professions: string[]
  season: string
  accent: string
}

export const DIRECTIONS: Direction[] = [
  {
    code: 'ССО',
    title: 'Строительное',
    desc: 'Капитальные стройки, энергообъекты и студенческие вахты по всей стране.',
    professions: ['Бетонщик', 'Арматурщик', 'Электромонтажник', 'Штукатур-маляр'],
    season: 'Июль — август · вахта',
    accent: 'от 90 000 ₽ / сезон',
  },
  {
    code: 'СПО',
    title: 'Педагогическое',
    desc: 'Вожатые детских лагерей: от Чёрного моря до Татарстана.',
    professions: ['Вожатый', 'Педагог-организатор', 'Инструктор по спорту'],
    season: 'Июнь — август · 3 смены',
    accent: 'от 65 000 ₽ / сезон',
  },
  {
    code: 'СОП',
    title: 'Проводники',
    desc: 'Поезда дальнего следования, форма, маршруты через всю Россию.',
    professions: ['Проводник пассажирского вагона', 'Бортпроводник'],
    season: 'Лето · РЖД',
    accent: 'от 85 000 ₽ / сезон',
  },
  {
    code: 'ССервО',
    title: 'Сервисное',
    desc: 'Отели, рестораны и курорты юга: сервис высокого класса.',
    professions: ['Официант', 'Бармен', 'Администратор', 'Повар'],
    season: 'Май — сентябрь · юг',
    accent: 'от 75 000 ₽ / сезон',
  },
  {
    code: 'СЭО',
    title: 'Энергетическое',
    desc: 'Фишка КГЭУ: подстанции, сети и энергообъекты.',
    professions: ['Электромонтёр', 'Оператор энергоустановок'],
    season: 'Лето · Сетевые компании',
    accent: 'от 95 000 ₽ / сезон',
  },
  {
    code: 'ОСД',
    title: 'Снежный десант',
    desc: 'Зимние выезды: помощь сёлам, концерты и профориентация.',
    professions: ['Волонтёр', 'Агитбригада', 'Мастер на все руки'],
    season: 'Январь — февраль',
    accent: 'добровольчество',
  },
]

export interface PresetQuestion {
  label: string
  question: string
  image: string
}

export const PRESET_QUESTIONS: PresetQuestion[] = [
  {
    label: 'Сколько заработаю?',
    question: 'Сколько зарабатывают бойцы штаба Тесла за целину и от чего зависит зарплата?',
    image: 'https://images.unsplash.com/photo-1541888946425-d81bb19240f5?w=800&q=80&auto=format&fit=crop',
  },
  {
    label: 'Какой отряд выбрать?',
    question: 'Какой отряд штаба Тесла выбрать новичку: стройка, вожатый, проводник или сервис?',
    image: 'https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=800&q=80&auto=format&fit=crop',
  },
  {
    label: 'Что такое целина?',
    question: 'Что такое целина и как проходит атмосфера третьего трудового семестра?',
    image: 'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&q=80&auto=format&fit=crop',
  },
  {
    label: 'Как попасть?',
    question: 'Как попасть в отряд штаба Тесла в 2026 году и что нужно для вступления?',
    image: 'https://images.unsplash.com/photo-1517486808906-6ca8b3f04846?w=800&q=80&auto=format&fit=crop',
  },
]

export interface Metric {
  value: string
  label: string
  desc: string
  span?: boolean
}

export const METRICS: Metric[] = [
  { value: '7', label: 'направлений', desc: 'Стройка, педагогика, проводники, сервис, энергетика, десант и производство.', span: true },
  { value: '18', label: 'отрядов', desc: 'Боевые единицы штаба — от «Исиды» до «Оникса».' },
  { value: '15+', label: 'регионов строек', desc: 'От Казани и Татарстана до юга, севера и дальних вахт.' },
  { value: '≈85 000 ₽', label: 'средний заработок', desc: 'За летний сезон в зависимости от направления.', span: true },
  { value: '№1', label: 'лучший штаб', desc: 'Кубки и знамёна лучшего штаба студенческих отрядов.' },
]

export interface TimelineItem {
  year: string
  title: string
  text: string
}

export const TIMELINE: TimelineItem[] = [
  { year: '2013', title: 'Рождение «Теслы»', text: 'В КГЭУ создан штаб студенческих отрядов. Первые стройки и выезды.' },
  { year: '2016', title: 'Первая целина', text: 'Отряды выходят на всероссийские стройки и детские лагеря.' },
  { year: '2019', title: 'Энергетический профиль', text: 'СЭО «Заряд» и «Высокое Напряжение» закрепляют фишку энергоуниверситета.' },
  { year: '2022', title: 'Снежный десант', text: '«Резонанс» и «Сириус» везут помощь в районы Татарстана.' },
  { year: '2024', title: 'Лучший штаб', text: '«Тесла» берёт кубок лучшего штаба и знамёна за целину.' },
  { year: '2026', title: 'Ограниченный набор', text: 'Открыт набор нового поколения бойцов. Твоя очередь.' },
]

export interface Alumni {
  name: string
  role: string
  text: string
  initials: string
}

export const ALUMNI: Alumni[] = [
  { name: 'Командир «Исиды»', role: 'ССО · выпуск 2021', text: '«Целина научила держать слово и бригаду. Сейчас руковожу участком на энергостройке».', initials: 'СИ' },
  { name: 'Вожатая «Дельты»', role: 'СПО · выпуск 2022', text: '«Три лета в лагере — и я выбрала педагогику профессией. Дети до сих пор пишут».', initials: 'ВД' },
  { name: 'Проводник Energy', role: 'СОП · выпуск 2023', text: '«Полстраны за лето, своя бригада и зарплата, которой хватило на магистратуру».', initials: 'ПЕ' },
]

export interface EventItem {
  title: string
  when: string
  desc: string
  tag: string
}

export const EVENTS: EventItem[] = [
  { title: 'Слёт отрядов «Тесла»', when: 'Октябрь', desc: 'Открытие года: посвящение кандидатов, знамёна и первые комиссарские сборы.', tag: 'главное' },
  { title: 'Школа бойцов «Погружение»', when: 'Ноябрь — апрель', desc: 'Профобучение, творческие кастинги и верёвочные курсы перед целиной.', tag: 'обучение' },
  { title: 'Фестиваль творчества', when: 'Март', desc: 'Театр, вокал, танец и отрядные легенды на большой сцене КГЭУ.', tag: 'творчество' },
  { title: 'Спартакиада РСО', when: 'Апрель', desc: 'Волейбол, футбол и сдача на значок. «Тесла» — всегда в призах.', tag: 'спорт' },
  { title: 'Целина — третий семестр', when: 'Июнь — август', desc: 'Работа, заработок и лучшее лето: стройки, лагеря, поезда и юг.', tag: 'сезон' },
  { title: 'Снежный десант', when: 'Январь — февраль', desc: 'Зимние выезды в сёла: помощь ветеранам, концерты, профориентация.', tag: 'зима' },
]

export interface Commander {
  role: string
  name: string
  desc: string
}

export const COMSOSTAV: Commander[] = [
  { role: 'Командир штаба', name: 'Командир', desc: 'Стратегия, стройки и знамя штаба.' },
  { role: 'Комиссар', name: 'Комиссар', desc: 'Люди, атмосфера и комиссарская работа.' },
  { role: 'Мастер', name: 'Мастер', desc: 'Трудоустройство, договоры и безопасность.' },
  { role: 'Пресс-служба', name: 'Пресс-секретарь', desc: 'Медиа, летопись и «ПрогрессLAB».' },
]
