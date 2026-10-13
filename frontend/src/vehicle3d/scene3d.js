// The 3D stage: renderer, camera, lights, the vehicle, and the effects for each job stage.
// Loaded lazily by Vehicle3D.jsx so three.js never weighs down the first page load.
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { buildVehicle, paintFor } from './models.js'

const TARGET = new THREE.Vector3(0, 0.6, 0)
const HIGHLIGHT = { focus: 0xff5b1f, waiting_approval: 0xffa000, done: 0x12a05c }
const IDLE_MS = 5000

function radialTexture(stops) {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  for (const [at, color] of stops) grad.addColorStop(at, color)
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

function points(count, size, color, texture, blending = THREE.NormalBlending) {
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3))
  const mat = new THREE.PointsMaterial({ size, color, map: texture, transparent: true, depthWrite: false, blending, sizeAttenuation: true })
  const p = new THREE.Points(geo, mat)
  p.frustumCulled = false
  p.visible = false
  return p
}

const rand = (a, b) => a + Math.random() * (b - a)

// Zones a vehicle doesn't have map to the closest one it does (a scooter's clutch lives in its CVT case).
const ALIASES = { scooter: { clutch: 'cvt', chain: 'cvt' }, motorcycle: { cvt: 'clutch' } }

export function createScene(canvas, { kind, plate, reducedMotion = false, onFrame, fixedAzimuth = null }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.05
  renderer.outputColorSpace = THREE.SRGBColorSpace

  const scene = new THREE.Scene()
  const pmrem = new THREE.PMREMGenerator(renderer)
  const envRT = pmrem.fromScene(new RoomEnvironment(), 0.04)
  scene.environment = envRT.texture
  scene.environmentIntensity = 0.6

  const camera = new THREE.PerspectiveCamera(32, 1, 0.05, 40)
  camera.position.set(1.7, 1.15, 2.6)

  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 0.6))
  const key = new THREE.DirectionalLight(0xffffff, 1.6)
  key.position.set(2, 3, 2.5)
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xbfd4ff, 0.9)
  rim.position.set(-2.5, 1.5, -2)
  scene.add(rim)

  // Soft contact shadow under the vehicle (cheaper than shadow maps, fine on low-end phones)
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 0.9),
    new THREE.MeshBasicMaterial({ map: radialTexture([[0, 'rgba(0,0,0,0.42)'], [0.55, 'rgba(0,0,0,0.16)'], [1, 'rgba(0,0,0,0)']]), transparent: true, depthWrite: false }))
  shadow.rotation.x = -Math.PI / 2
  shadow.position.y = 0.002
  scene.add(shadow)

  const ring = new THREE.Mesh(new THREE.RingGeometry(1.05, 1.12, 96),
    new THREE.MeshBasicMaterial({ color: HIGHLIGHT.done, transparent: true, opacity: 0, depthWrite: false }))
  ring.rotation.x = -Math.PI / 2
  ring.position.y = 0.003
  scene.add(ring)

  const vehicle = buildVehicle(kind, { paint: paintFor(kind, plate), plate })
  scene.add(vehicle.group)
  for (const z of Object.values(vehicle.zones)) {
    for (const mesh of z.meshes) mesh.userData.base = { emissive: mesh.material.emissive?.clone(), intensity: mesh.material.emissiveIntensity ?? 0 }
  }

  // Marker: a pulsing halo drawn on top of everything at the focused part
  const dot = radialTexture([[0, 'rgba(255,255,255,1)'], [0.25, 'rgba(255,255,255,0.9)'], [0.32, 'rgba(255,255,255,0)'],
    [0.6, 'rgba(255,255,255,0)'], [0.68, 'rgba(255,255,255,0.85)'], [0.76, 'rgba(255,255,255,0)']])
  const marker = new THREE.Sprite(new THREE.SpriteMaterial({ map: dot, color: HIGHLIGHT.focus, depthTest: false, transparent: true }))
  marker.renderOrder = 10
  marker.visible = false
  scene.add(marker)

  // Effects
  const soft = radialTexture([[0, 'rgba(255,255,255,1)'], [0.5, 'rgba(255,255,255,0.6)'], [1, 'rgba(255,255,255,0)']])
  const water = points(700, 0.03, 0x4aa8ff, soft)
  const sparks = points(140, 0.03, 0xffb066, soft, THREE.AdditiveBlending)
  const twinkle = points(90, 0.065, 0xffc94a, soft)
  scene.add(water, sparks, twinkle)
  const waterVel = new Float32Array(700)
  const sparkVel = new Float32Array(140 * 3)
  const sparkLife = new Float32Array(140)

  const foamGeo = new THREE.SphereGeometry(1, 12, 8)
  const foamMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.35, metalness: 0, transparent: true, opacity: 0.92 })
  const foam = new THREE.InstancedMesh(foamGeo, foamMat, 70)
  foam.visible = false
  scene.add(foam)
  const foamSpots = []
  {
    // Sit the foam on the vehicle's top surfaces by sampling its bounding box from above
    const box = new THREE.Box3().setFromObject(vehicle.group)
    const ray = new THREE.Raycaster()
    while (foamSpots.length < 70) {
      const x = rand(box.min.x + 0.1, box.max.x - 0.1)
      const z = rand(-0.12, 0.12)
      ray.set(new THREE.Vector3(x, 2, z), new THREE.Vector3(0, -1, 0))
      const hit = ray.intersectObject(vehicle.group, true)[0]
      if (hit && hit.point.y > 0.3) foamSpots.push({ p: hit.point, s: rand(0.018, 0.04), ph: rand(0, 6.28) })
    }
  }

  const controls = new OrbitControls(camera, canvas)
  controls.target.copy(TARGET)
  controls.enableDamping = true
  controls.enablePan = false
  controls.minDistance = 1.7
  controls.maxDistance = 4.2
  controls.minPolarAngle = 0.32 * Math.PI
  controls.maxPolarAngle = 0.5 * Math.PI
  controls.rotateSpeed = 0.7
  let lastTouch = -Infinity
  controls.addEventListener('start', () => { lastTouch = performance.now() })
  controls.addEventListener('end', () => { lastTouch = performance.now() })
  controls.update()

  let state = { stage: 'intake', zones: [], focus: null }
  let lit = []
  let placed = false
  let focusAzimuth = 0.75
  let sparkOrigin = new THREE.Vector3()
  let active = true
  let frame = 0
  let last = performance.now()
  let time = 0
  const sph = new THREE.Spherical()
  const tmp = new THREE.Vector3()

  function setState(next) {
    state = { ...state, ...next }
    for (const mesh of lit) {
      const b = mesh.userData.base
      if (b.emissive) mesh.material.emissive.copy(b.emissive)
      mesh.material.emissiveIntensity = b.intensity
    }
    const showFocus = state.focus && state.stage !== 'washing' && state.stage !== 'done'
    const own = (z) => (vehicle.zones[z] ? z : ALIASES[kind]?.[z])
    lit = showFocus ? [...new Set(state.zones.map(own))].flatMap((z) => vehicle.zones[z]?.meshes || []) : []
    const zone = showFocus ? vehicle.zones[own(state.focus)] : null
    marker.visible = !!zone
    if (zone) {
      marker.position.copy(zone.anchor)
      marker.material.color.set(state.stage === 'waiting_approval' ? HIGHLIGHT.waiting_approval : HIGHLIGHT.focus)
      // Face the side the part is on (clutch on the right, chain on the left)
      const side = zone.anchor.z < -0.03 ? -1 : 1
      focusAzimuth = Math.atan2(zone.anchor.x * 0.9 + 0.25 * side, side)
      sparkOrigin.copy(zone.anchor)
      lastTouch = -Infinity
    } else {
      focusAzimuth = 0.75
    }
    if (!placed && fixedAzimuth == null) {
      // First view: start already facing the part instead of swinging round to it
      placed = true
      tmp.copy(camera.position).sub(controls.target)
      sph.setFromVector3(tmp)
      sph.theta = focusAzimuth
      sph.phi = 1.2
      sph.radius = zone ? 2.75 : 3.15
      camera.position.copy(controls.target).add(tmp.setFromSpherical(sph))
      controls.update()
    }
    water.visible = foam.visible = state.stage === 'washing'
    sparks.visible = state.stage === 'service' && !!zone
    twinkle.visible = state.stage === 'done'
    if (water.visible) resetWater(true)
    if (twinkle.visible) resetTwinkle()
    if (reducedMotion) {
      step(0) // static highlight, no movement
      render()
    }
  }

  function resetWater(all) {
    const pos = water.geometry.attributes.position.array
    for (let i = 0; i < waterVel.length; i++) {
      if (!all && pos[i * 3 + 1] > 0) continue
      pos[i * 3] = rand(-0.95, 0.95)
      pos[i * 3 + 1] = all ? rand(0, 1.7) : rand(1.5, 1.8)
      pos[i * 3 + 2] = rand(-0.35, 0.35)
      waterVel[i] = rand(1.6, 2.6)
    }
    water.geometry.attributes.position.needsUpdate = true
  }

  function resetTwinkle() {
    const pos = twinkle.geometry.attributes.position.array
    const box = new THREE.Box3().setFromObject(vehicle.group)
    for (let i = 0; i < 90; i++) {
      pos[i * 3] = rand(box.min.x, box.max.x)
      pos[i * 3 + 1] = rand(0.2, box.max.y + 0.1)
      pos[i * 3 + 2] = rand(-0.3, 0.3)
    }
    twinkle.geometry.attributes.position.needsUpdate = true
  }

  function step(dt) {
    time += dt
    const pulse = 0.5 + 0.5 * Math.sin(time * (state.stage === 'waiting_approval' ? 5.5 : 3.2))
    const color = state.stage === 'waiting_approval' ? HIGHLIGHT.waiting_approval : HIGHLIGHT.focus
    for (const mesh of lit) {
      mesh.material.emissive.set(color)
      mesh.material.emissiveIntensity = 0.35 + pulse * 0.9
    }
    if (marker.visible) {
      const s = 0.13 + pulse * 0.05
      marker.scale.set(s, s, 1)
      marker.material.opacity = 0.55 + pulse * 0.45
    }
    ring.material.opacity += ((state.stage === 'done' ? 0.55 : 0) - ring.material.opacity) * Math.min(1, dt * 3)

    if (water.visible) {
      const pos = water.geometry.attributes.position.array
      for (let i = 0; i < waterVel.length; i++) {
        pos[i * 3 + 1] -= waterVel[i] * dt
        pos[i * 3] += dt * 0.08
      }
      water.geometry.attributes.position.needsUpdate = true
      resetWater(false)
      const m = new THREE.Matrix4()
      foamSpots.forEach((f, i) => {
        const s = f.s * (0.85 + 0.25 * Math.sin(time * 2.2 + f.ph))
        m.makeScale(s, s * 0.8, s).setPosition(f.p.x, f.p.y + s * 0.4, f.p.z)
        foam.setMatrixAt(i, m)
      })
      foam.instanceMatrix.needsUpdate = true
    }
    if (sparks.visible) {
      const pos = sparks.geometry.attributes.position.array
      for (let i = 0; i < 140; i++) {
        sparkLife[i] -= dt
        if (sparkLife[i] <= 0) {
          sparkLife[i] = rand(0.3, 0.9)
          pos[i * 3] = sparkOrigin.x; pos[i * 3 + 1] = sparkOrigin.y; pos[i * 3 + 2] = sparkOrigin.z
          sparkVel[i * 3] = rand(-0.6, 0.6); sparkVel[i * 3 + 1] = rand(0.2, 1.1); sparkVel[i * 3 + 2] = rand(-0.6, 0.6)
        }
        sparkVel[i * 3 + 1] -= 2.5 * dt
        pos[i * 3] += sparkVel[i * 3] * dt
        pos[i * 3 + 1] += sparkVel[i * 3 + 1] * dt
        pos[i * 3 + 2] += sparkVel[i * 3 + 2] * dt
      }
      sparks.geometry.attributes.position.needsUpdate = true
    }
    if (twinkle.visible) twinkle.material.opacity = 0.55 + 0.45 * Math.sin(time * 4)

    // Idle camera: sway around the focused part, or turn slowly to show the whole vehicle
    if (!reducedMotion && performance.now() - lastTouch > IDLE_MS) {
      tmp.copy(camera.position).sub(controls.target)
      sph.setFromVector3(tmp)
      const want = fixedAzimuth != null ? fixedAzimuth : marker.visible ? focusAzimuth + 0.22 * Math.sin(time * 0.6) : sph.theta + dt * 0.28
      let d = want - sph.theta
      d = Math.atan2(Math.sin(d), Math.cos(d))
      sph.theta += fixedAzimuth != null ? d : d * Math.min(1, dt * (marker.visible ? 1.6 : 4))
      sph.phi += (1.2 - sph.phi) * Math.min(1, dt * 1.5)
      sph.radius += ((marker.visible ? 2.75 : 3.15) - sph.radius) * Math.min(1, dt * 1.2)
      camera.position.copy(controls.target).add(tmp.setFromSpherical(sph))
    }
    controls.update()
  }

  function render() {
    renderer.render(scene, camera)
    onFrame?.()
  }

  function loop() {
    frame = requestAnimationFrame(loop)
    const now = performance.now()
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    if (!reducedMotion) step(dt)
    else controls.update()
    render()
  }

  function setActive(on) {
    if (on === active) return
    active = on
    cancelAnimationFrame(frame)
    if (on) {
      last = performance.now()
      loop()
    }
  }

  function resize(w, h) {
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    // Narrow (phone) views step back a little so the whole vehicle fits
    camera.fov = w / h < 1.2 ? 40 : 32
    camera.updateProjectionMatrix()
    render()
  }

  // Screen position of the focused part, for the HTML label
  function anchorOnScreen() {
    if (!marker.visible) return null
    tmp.copy(marker.position).project(camera)
    const el = renderer.domElement
    return { x: (tmp.x + 1) / 2 * el.clientWidth, y: (1 - tmp.y) / 2 * el.clientHeight, visible: tmp.z < 1 }
  }

  function dispose() {
    cancelAnimationFrame(frame)
    controls.dispose()
    scene.traverse((o) => {
      o.geometry?.dispose()
      const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
      for (const m of mats) { m.map?.dispose(); m.dispose() }
    })
    envRT.dispose()
    pmrem.dispose()
    renderer.dispose()
  }

  loop()
  return { setState, setActive, resize, anchorOnScreen, dispose }
}
