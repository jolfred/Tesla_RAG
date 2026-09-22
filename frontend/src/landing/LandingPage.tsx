import React from 'react'
import { motion } from 'framer-motion'

import AiLetopis from './AiLetopis'
import MagneticField from './MagneticField'
import teslaHeaderLogo from '../assets/logos/tesla.jpg'
import { ALUMNI, COMSOSTAV, DIRECTIONS, EVENTS, METRICS, SQUADS, TIMELINE, kgeuLogo, trudKrutLogo, trudLogo } from './data'

// Каскад Hero: строки проявляются сверху вниз, blur(10px)->0, y 15->0.
// Размытие длинное (1.4с на строку — в два раза дольше базового)

// Единая рамка логотипа: все эмблемы (любых исходных размеров) — в одинаковый круг 44px.
// Grayscale->цвет при наведении наследуется от .marquee-item (фильтр на родителе).
function SquadEmblem({ name, emblem, logo }: { name: string; emblem: string; logo?: string }): React.JSX.Element {
  const frame: React.CSSProperties = {
    width: 44,
    height: 44,
    minWidth: 44,
    borderRadius: 999,
    overflow: 'hidden',
    border: '1px solid rgba(122,62,230,0.35)',
    background: '#0B0A12',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }
  if (logo) {
    return (
      <span style={frame}>
        <img src={logo} alt={`Логотип ${name}`} loading="lazy" width={44} height={44} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
      </span>
    )
  }
  return (
    <span style={frame}>
      <span style={{ fontSize: 20, color: '#9D65FF', lineHeight: 1 }}>{emblem}</span>
    </span>
  )
}
const heroContainer = {
  hidden: {},
  show: { transition: { staggerChildren: 0.22, delayChildren: 0.1 } },
}
const heroLine = {
  hidden: { opacity: 0, y: 15, filter: 'blur(10px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 1.4, ease: [0.22, 1, 0.36, 1] as const } },
}

const reveal = {
  hidden: { opacity: 0, y: 28, filter: 'blur(6px)' },
  show: { opacity: 1, y: 0, filter: 'blur(0px)', transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] as const } },
}

function SectionTitle({ kicker, title, sub }: { kicker: string; title: string; sub?: string }): React.JSX.Element {
  return (
    <motion.div variants={reveal} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-80px' }} style={{ maxWidth: 760 }}>
      <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#9D65FF', marginBottom: 10 }}>
        {kicker}
      </div>
      <h2 className="tesla-display" style={{ fontSize: 'clamp(26px, 4vw, 40px)', lineHeight: 1.12, margin: 0 }}>
        {title}
      </h2>
      {sub && <p style={{ color: '#B9B0D6', fontSize: 15, lineHeight: 1.65, marginTop: 10 }}>{sub}</p>}
    </motion.div>
  )
}

function Header(): React.JSX.Element {
  return (
    <motion.header
      variants={heroLine}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '18px 0',
        position: 'relative',
        zIndex: 2,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <img
          src={teslaHeaderLogo}
          alt="Логотип штаба Тесла"
          width={80}
          height={80}
          style={{ width: 80, height: 80, borderRadius: 20, objectFit: 'cover', boxShadow: '0 0 32px rgba(122,62,230,0.55)' }}
        />
        <div>
          <div className="tesla-display" style={{ fontWeight: 700, fontSize: 19 }}>Тесла</div>
          <div style={{ fontSize: 12, color: '#8E86A8', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Штаб СО КГЭУ</div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <a
          href="/wiki"
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: '#D9CCFF',
            textDecoration: 'none',
            border: '1px solid rgba(255,255,255,0.16)',
            borderRadius: 999,
            padding: '8px 16px',
          }}
        >
          Летопись →
        </a>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 12,
            fontWeight: 700,
            border: '1px solid rgba(122,62,230,0.4)',
            background: 'rgba(122,62,230,0.12)',
            borderRadius: 999,
            padding: '8px 14px',
            color: '#D9CCFF',
          }}
        >
          <span style={{ width: 8, height: 8, borderRadius: 999, background: '#9D65FF', animation: 'pulseGlow 3.2s ease-in-out infinite' }} />
          Ограниченный набор 2026 активен
        </div>
      </div>
    </motion.header>
  )
}

function Marquee(): React.JSX.Element {
  const row = [...SQUADS, ...SQUADS]
  return (
    <section aria-label="Лента отрядов" style={{ borderTop: '1px solid rgba(122,62,230,0.2)', borderBottom: '1px solid rgba(122,62,230,0.2)', overflow: 'hidden', background: 'rgba(7,6,10,0.7)' }}>
      <div className="marquee-track" style={{ padding: '18px 0' }}>
        {row.map((s, i) => (
          <a
            key={`${s.name}-${i}`}
            href={s.vk}
            target="_blank"
            rel="noreferrer"
            className="marquee-item"
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 28px', textDecoration: 'none', color: '#EAE4FF', whiteSpace: 'nowrap' }}
          >
            <SquadEmblem name={s.name} emblem={s.emblem} logo={s.logo} />
            <span style={{ fontWeight: 700, fontSize: 14 }}>{s.name}</span>
            <span style={{ fontSize: 11, color: '#8E86A8', border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '2px 8px' }}>{s.tag}</span>
          </a>
        ))}
      </div>
    </section>
  )
}

export default function LandingPage(): React.JSX.Element {
  return (
    <div style={{ background: '#07060A', minHeight: '100vh', color: '#F2EFFF' }}>
      {/* HERO */}
      <section style={{ position: 'relative', overflow: 'hidden' }}>
        <MagneticField />
        <motion.div
          variants={heroContainer}
          initial="hidden"
          animate="show"
          style={{ position: 'relative', zIndex: 1, maxWidth: 1120, margin: '0 auto', padding: '0 20px 72px' }}
        >
          <Header />
          <div style={{ textAlign: 'center', marginTop: 48 }}>
            <motion.div variants={heroLine}>
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 700,
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  color: '#C9B8FF',
                  border: '1px solid rgba(122,62,230,0.35)',
                  borderRadius: 999,
                  padding: '7px 14px',
                  background: 'rgba(17,15,24,0.6)',
                }}
              >
                Лимитированный премиум · Штаб студенческих отрядов
              </span>
            </motion.div>
            <motion.h1
              variants={heroLine}
              className="tesla-display text-balance"
              style={{ fontSize: 'clamp(34px, 6vw, 68px)', lineHeight: 1.05, margin: '22px 0 0', fontWeight: 700 }}
            >
              Твоё самое незабываемое
              <br />
              <span style={{ background: 'linear-gradient(92deg, #9D65FF, #7A3EE6 60%, #D9CCFF)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
                лето начинается здесь
              </span>
            </motion.h1>
            <motion.p variants={heroLine} style={{ color: '#B9B0D6', fontSize: 'clamp(15px, 2vw, 18px)', maxWidth: 640, margin: '18px auto 0', lineHeight: 1.65 }}>
              18 отрядов, 7 направлений, настоящая зарплата и люди, с которыми хочется идти в целину. Спроси архив — ответит ИИ Летопись.
            </motion.p>
            <motion.div variants={heroLine}>
              <AiLetopis />
            </motion.div>
          </div>
        </motion.div>
      </section>

      <Marquee />

      {/* НАПРАВЛЕНИЯ */}
      <section style={{ maxWidth: 1120, margin: '0 auto', padding: '84px 20px 12px' }}>
        <SectionTitle kicker="Направления" title="Выбери своё направление — профессию дадим до лета" sub="Бесплатное профобучение зимой и весной: корочки, практика и наставник из боевых отрядов." />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14, marginTop: 28 }}>
          {DIRECTIONS.map((d, i) => (
            <motion.div
              key={d.code}
              variants={reveal}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: '-60px' }}
              whileHover={{ y: -4 }}
              className="glass-card"
              style={{ borderRadius: 20, padding: 22 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="tesla-display" style={{ fontSize: 13, fontWeight: 700, color: '#9D65FF', letterSpacing: '0.1em' }}>{d.code}</span>
                <span style={{ fontSize: 12, color: '#8E86A8' }}>{d.season}</span>
              </div>
              <h3 className="tesla-display" style={{ fontSize: 20, margin: '10px 0 8px' }}>{d.title}</h3>
              <p style={{ fontSize: 14, color: '#B9B0D6', lineHeight: 1.6, margin: 0 }}>{d.desc}</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 14 }}>
                {d.professions.map((p) => (
                  <span key={p} style={{ fontSize: 12, background: 'rgba(122,62,230,0.14)', border: '1px solid rgba(122,62,230,0.3)', borderRadius: 999, padding: '5px 10px', color: '#D9CCFF' }}>
                    {p}
                  </span>
                ))}
              </div>
              <div style={{ marginTop: 14, fontSize: 13, fontWeight: 800, color: '#fff' }}>
                <span style={{ color: '#9D65FF' }}>0{i + 1} · </span>{d.accent}
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* БЕНТО */}
      <section style={{ maxWidth: 1120, margin: '0 auto', padding: '72px 20px 12px' }}>
        <SectionTitle kicker="Почему Тесла" title="Бенто побед: цифры вместо обещаний" />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 14, marginTop: 28 }} className="bento-grid">
          {METRICS.map((m) => (
            <motion.div
              key={m.label}
              variants={reveal}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: '-60px' }}
              whileHover={{ y: -4 }}
              className="glass-card"
              style={{
                borderRadius: 20,
                padding: 24,
                gridColumn: m.span ? 'span 3' : 'span 2',
                background: m.span ? 'linear-gradient(135deg, rgba(122,62,230,0.22), rgba(17,15,24,0.8))' : undefined,
              }}
            >
              <div className="tesla-display" style={{ fontSize: 'clamp(30px, 4vw, 46px)', fontWeight: 700, color: '#fff' }}>{m.value}</div>
              <div style={{ fontSize: 14, fontWeight: 800, color: '#9D65FF', marginTop: 4 }}>{m.label}</div>
              <div style={{ fontSize: 13.5, color: '#B9B0D6', marginTop: 6, lineHeight: 1.55 }}>{m.desc}</div>
            </motion.div>
          ))}
        </div>
        <style>{'@media (max-width: 760px) { .bento-grid { grid-template-columns: 1fr 1fr !important; } .bento-grid > div { grid-column: span 1 !important; } .bento-grid > div:first-child, .bento-grid > div:nth-child(4) { grid-column: span 2 !important; } }'}</style>
      </section>

      {/* ИСТОРИЯ */}
      <section style={{ maxWidth: 1120, margin: '0 auto', padding: '72px 20px 12px' }}>
        <SectionTitle kicker="История" title="От первой стройки — до лучшего штаба" sub="Сжатый таймлайн вех и выпускники, которыми гордится «Тесла»." />
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 14, marginTop: 28 }} className="history-grid">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {TIMELINE.map((t, i) => (
              <motion.div
                key={t.year}
                variants={reveal}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: '-40px' }}
                className="glass-card"
                style={{ borderRadius: 16, padding: '16px 18px', display: 'flex', gap: 16, alignItems: 'flex-start' }}
              >
                <div className="tesla-display" style={{ minWidth: 58, fontWeight: 700, color: i === TIMELINE.length - 1 ? '#fff' : '#9D65FF', background: i === TIMELINE.length - 1 ? '#7A3EE6' : 'rgba(122,62,230,0.14)', borderRadius: 10, textAlign: 'center', padding: '6px 0', fontSize: 14 }}>
                  {t.year}
                </div>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15 }}>{t.title}</div>
                  <div style={{ fontSize: 13.5, color: '#B9B0D6', marginTop: 4, lineHeight: 1.55 }}>{t.text}</div>
                </div>
              </motion.div>
            ))}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {ALUMNI.map((a) => (
              <motion.div key={a.name} variants={reveal} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }} className="glass-card" style={{ borderRadius: 16, padding: 20 }}>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <div style={{ width: 46, height: 46, borderRadius: 999, background: 'linear-gradient(135deg,#7A3EE6,#9D65FF)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800 }}>{a.initials}</div>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>{a.name}</div>
                    <div style={{ fontSize: 12, color: '#9D65FF' }}>{a.role}</div>
                  </div>
                </div>
                <p style={{ fontSize: 13.5, color: '#CFC6EC', lineHeight: 1.6, margin: '12px 0 0' }}>{a.text}</p>
              </motion.div>
            ))}
            <div className="glass-card" style={{ borderRadius: 16, overflow: 'hidden' }}>
              <img src="https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=800&q=80&auto=format&fit=crop" alt="Бойцы отрядов" loading="lazy" style={{ width: '100%', height: 190, objectFit: 'cover', display: 'block' }} />
            </div>
          </div>
        </div>
        <style>{'@media (max-width: 860px) { .history-grid { grid-template-columns: 1fr !important; } }'}</style>
      </section>

      {/* МЕРОПРИЯТИЯ + СТРУКТУРА */}
      <section style={{ maxWidth: 1120, margin: '0 auto', padding: '72px 20px 12px' }}>
        <SectionTitle kicker="Жизнь штаба" title="Мероприятия года и комсостав" sub="Год бойца расписан по месяцам: от посвящения до целины. Рядом — люди, которые держат штаб." />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14, marginTop: 28 }}>
          {EVENTS.map((e) => (
            <motion.div key={e.title} variants={reveal} initial="hidden" whileInView="show" viewport={{ once: true, margin: '-40px' }} whileHover={{ y: -4 }} className="glass-card" style={{ borderRadius: 20, padding: 22 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#9D65FF' }}>{e.tag}</span>
                <span style={{ fontSize: 12, color: '#8E86A8' }}>{e.when}</span>
              </div>
              <h3 style={{ fontSize: 17, margin: '10px 0 6px' }}>{e.title}</h3>
              <p style={{ fontSize: 13.5, color: '#B9B0D6', lineHeight: 1.6, margin: 0 }}>{e.desc}</p>
            </motion.div>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 14, marginTop: 14 }}>
          {COMSOSTAV.map((c) => (
            <motion.div key={c.role} variants={reveal} initial="hidden" whileInView="show" viewport={{ once: true }} className="glass-card" style={{ borderRadius: 18, padding: 20, textAlign: 'center' }}>
              <div style={{ width: 52, height: 52, borderRadius: 16, margin: '0 auto', background: 'rgba(122,62,230,0.16)', border: '1px solid rgba(122,62,230,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22 }}>✦</div>
              <div style={{ fontSize: 12, color: '#9D65FF', fontWeight: 800, marginTop: 10, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{c.role}</div>
              <div style={{ fontWeight: 700, marginTop: 4 }}>{c.name}</div>
              <div style={{ fontSize: 13, color: '#B9B0D6', marginTop: 4 }}>{c.desc}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section style={{ maxWidth: 1120, margin: '0 auto', padding: '72px 20px 90px' }}>
        <motion.div
          variants={reveal}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, margin: '-80px' }}
          className="glass-card"
          style={{
            borderRadius: 28,
            padding: 'clamp(28px, 5vw, 64px)',
            textAlign: 'center',
            position: 'relative',
            overflow: 'hidden',
            background: 'linear-gradient(180deg, rgba(122,62,230,0.2), rgba(17,15,24,0.9))',
          }}
        >
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(520px 240px at 50% 0%, rgba(157,101,255,0.35), transparent 70%)', pointerEvents: 'none' }} />
          <div style={{ position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginBottom: 6 }}>
              <img src={trudKrutLogo} alt="Труд крут" loading="lazy" width={52} height={52} style={{ width: 52, height: 52, borderRadius: 999, objectFit: 'cover', border: '1px solid rgba(157,101,255,0.5)' }} />
              <img src={trudLogo} alt="Труд" loading="lazy" width={52} height={52} style={{ width: 52, height: 52, borderRadius: 999, objectFit: 'cover', border: '1px solid rgba(157,101,255,0.5)' }} />
            </div>
            <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#D9CCFF' }}>Мест в наборе 2026 — ограниченное число</div>
            <h2 className="tesla-display" style={{ fontSize: 'clamp(28px, 5vw, 52px)', margin: '14px 0 0', lineHeight: 1.08 }}>
              Займи своё место в строю
            </h2>
            <p style={{ color: '#CFC6EC', maxWidth: 560, margin: '14px auto 0', lineHeight: 1.65 }}>
              Оставь заявку — комсостав свяжется, подберёт отряд и запишет в школу бойцов «Погружение».
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 26, flexWrap: 'wrap' }}>
              <motion.a
                href="https://vk.ru/rso_tesla"
                target="_blank"
                rel="noreferrer"
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.98 }}
                style={{ background: '#7A3EE6', color: '#fff', fontWeight: 800, fontSize: 16, borderRadius: 16, padding: '16px 34px', textDecoration: 'none', boxShadow: '0 0 32px rgba(122,62,230,0.55)' }}
              >
                Подать заявку в отряд
              </motion.a>
              <a
                href="https://vk.ru/rso_tesla"
                target="_blank"
                rel="noreferrer"
                style={{ border: '1px solid rgba(157,101,255,0.5)', color: '#D9CCFF', fontWeight: 700, fontSize: 15, borderRadius: 16, padding: '16px 26px', textDecoration: 'none' }}
              >
                Написать в сообщения штаба
              </a>
            </div>
          </div>
        </motion.div>
        <footer>
          <div className="footer-squads" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 18, padding: '34px 0 8px', borderTop: '1px solid rgba(122,62,230,0.2)' }}>
            {Object.entries(
              SQUADS.reduce<Record<string, typeof SQUADS>>((acc, s) => {
                ;(acc[s.direction] = acc[s.direction] || []).push(s)
                return acc
              }, {}),
            ).map(([direction, squads]) => (
              <div key={direction}>
                <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#9D65FF', marginBottom: 10 }}>
                  {direction}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {squads.map((s) => (
                    <a key={s.name} href={s.vk} target="_blank" rel="noreferrer" style={{ fontSize: 13.5, color: '#CFC6EC', textDecoration: 'none' }}>
                      {s.name}
                    </a>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginTop: 22, paddingBottom: 8, color: '#8E86A8', fontSize: 12, alignItems: 'center' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <img src={kgeuLogo} alt="КГЭУ" loading="lazy" width={30} height={30} style={{ width: 30, height: 30, borderRadius: 999, objectFit: 'cover', border: '1px solid rgba(122,62,230,0.35)' }} />
              Штаб студенческих отрядов КГЭУ «Тесла» · Летопись на RAG-архиве постов
            </span>
            <span className="tesla-display" style={{ fontWeight: 700, fontSize: 14, background: 'linear-gradient(92deg, #9D65FF, #D9CCFF)', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>
              Только Тесла — только Победа
            </span>
          </div>
          <div style={{ display: 'flex', gap: 16, paddingBottom: 26, fontSize: 12 }}>
            <a href="/api/v1/status" style={{ color: '#9D65FF', textDecoration: 'none' }}>status</a>
            <a href="https://vk.ru/rso_tesla" target="_blank" rel="noreferrer" style={{ color: '#9D65FF', textDecoration: 'none' }}>vk → rso_tesla</a>
          </div>
        </footer>
      </section>
    </div>
  )
}
