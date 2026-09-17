import React, { useEffect, useRef } from 'react'

const VERT = `
attribute vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`

const FRAG = `
precision mediump float;
uniform vec2 u_res;
uniform float u_time;
uniform vec2 u_mouse;
uniform vec2 u_mouse2;
uniform float u_active;

vec3 violet(float t) {
  vec3 a = vec3(0.478, 0.243, 0.902);
  vec3 b = vec3(0.616, 0.396, 1.0);
  return mix(a, b, t);
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float aspect = u_res.x / u_res.y;
  vec2 p = vec2(uv.x * aspect, uv.y);
  vec2 m1 = vec2(u_mouse.x * aspect, u_mouse.y);
  vec2 m2 = vec2(u_mouse2.x * aspect, u_mouse2.y);

  // Магнитное поле: два полюса (курсор + инерционный след)
  vec2 d1 = p - m1;
  vec2 d2 = p - m2;
  float r1 = length(d1) + 1e-4;
  float r2 = length(d2) + 1e-4;

  float field = exp(-r1 * 3.2) * u_active + exp(-r2 * 4.5) * u_active * 0.55;
  vec2 dir = normalize(d1 / (r1 * r1 + 0.08) + d2 / (r2 * r2 + 0.12) + 1e-5);
  vec2 warp = dir * field * 0.16;

  vec2 q = p + warp;
  q.x += sin(q.y * 6.0 + u_time * 0.35) * 0.012;
  q.y += cos(q.x * 5.0 - u_time * 0.28) * 0.012;

  // Тонкие световые линии-сетка
  vec2 grid = abs(fract(q * vec2(14.0, 10.0)) - 0.5);
  float lineX = smoothstep(0.48, 0.5, grid.x);
  float lineY = smoothstep(0.48, 0.5, grid.y);
  float lines = max(lineX, lineY);

  // Диагональные нити
  float diag = abs(fract((q.x + q.y) * 9.0 + u_time * 0.05) - 0.5);
  float diagLine = smoothstep(0.485, 0.5, diag) * 0.5;

  vec3 base = vec3(0.027, 0.024, 0.039);
  vec3 glow = violet(clamp(field, 0.0, 1.0)) * field * 0.85;
  vec3 lineCol = mix(vec3(0.10, 0.08, 0.16), vec3(0.55, 0.38, 1.0), clamp(field * 1.4, 0.0, 1.0));
  vec3 col = base + glow * 0.6 + lineCol * (lines * (0.10 + field * 0.75) + diagLine * (0.06 + field * 0.4));

  // Виньетка
  float vig = smoothstep(1.15, 0.35, length(uv - 0.5) * 1.6);
  col *= mix(0.75, 1.0, vig);

  gl_FragColor = vec4(col, 1.0);
}
`

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader {
  const sh = gl.createShader(type)
  if (!sh) throw new Error('shader alloc failed')
  gl.shaderSource(sh, src)
  gl.compileShader(sh)
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    throw new Error(`shader compile: ${gl.getShaderInfoLog(sh)}`)
  }
  return sh
}

/**
 * WebGL-фон «магнитное поле»: сетка тонких световых линий
 * изгибается вокруг курсора + инерционный след.
 */
export default function MagneticField({ className = '' }: { className?: string }): React.JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const gl = canvas.getContext('webgl', { antialias: false, alpha: false })
    if (!gl) return

    let prog: WebGLProgram | null = null
    let raf = 0
    let running = true
    const DPR = Math.min(window.devicePixelRatio || 1, 1.75)

    try {
      prog = gl.createProgram()
      if (!prog) return
      gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT))
      gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG))
      gl.linkProgram(prog)
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return
      gl.useProgram(prog)
    } catch {
      return
    }

    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(prog, 'a_pos')
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)

    const uRes = gl.getUniformLocation(prog, 'u_res')
    const uTime = gl.getUniformLocation(prog, 'u_time')
    const uMouse = gl.getUniformLocation(prog, 'u_mouse')
    const uMouse2 = gl.getUniformLocation(prog, 'u_mouse2')
    const uActive = gl.getUniformLocation(prog, 'u_active')

    const target = { x: 0.5, y: 0.5 }
    const smooth = { x: 0.5, y: 0.5 }
    const trail = { x: 0.5, y: 0.5 }
    let active = 0
    let activeTarget = 0
    const t0 = performance.now()

    const onMove = (e: PointerEvent): void => {
      const r = wrap.getBoundingClientRect()
      const x = (e.clientX - r.left) / Math.max(r.width, 1)
      const y = 1 - (e.clientY - r.top) / Math.max(r.height, 1)
      target.x = Math.min(1.05, Math.max(-0.05, x))
      target.y = Math.min(1.05, Math.max(-0.05, y))
      activeTarget = 1
    }
    const onLeave = (): void => {
      activeTarget = 0
    }
    // Слушаем всё окно — эффект живёт и за пределами hero
    window.addEventListener('pointermove', onMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave)

    const resize = (): void => {
      const r = wrap.getBoundingClientRect()
      const w = Math.max(2, Math.floor(r.width * DPR))
      const h = Math.max(2, Math.floor(r.height * DPR))
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
        gl.viewport(0, 0, w, h)
      }
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(wrap)

    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

    const frame = (): void => {
      if (!running) return
      const t = (performance.now() - t0) / 1000
      // Инерция: курсор + отстающий след = «магнитное» изгибание
      const k = reduced ? 1 : 0.075
      smooth.x += (target.x - smooth.x) * k
      smooth.y += (target.y - smooth.y) * k
      trail.x += (smooth.x - trail.x) * 0.035
      trail.y += (smooth.y - trail.y) * 0.035
      active += (activeTarget - active) * 0.06

      gl.uniform2f(uRes, canvas.width, canvas.height)
      gl.uniform1f(uTime, t)
      gl.uniform2f(uMouse, smooth.x, smooth.y)
      gl.uniform2f(uMouse2, trail.x, trail.y)
      gl.uniform1f(uActive, active)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)

    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro.disconnect()
      window.removeEventListener('pointermove', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
    }
  }, [])

  return (
    <div ref={wrapRef} className={className} aria-hidden="true" style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />
      {/* Мягкая фиолетовая подложка поверх шейдера */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          background:
            'radial-gradient(640px 320px at 50% 42%, rgba(122,62,230,0.16), transparent 70%), linear-gradient(to bottom, rgba(7,6,10,0.1), rgba(7,6,10,0.72))',
        }}
      />
    </div>
  )
}
