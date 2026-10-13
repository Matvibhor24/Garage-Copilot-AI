// The owner's 3D garage floor: stations painted on the floor, the vehicles on it (the same models as the job
// view), mechanics by the vehicle they're working on. Vehicles glide to their new station when a job moves on.
// Loaded lazily by GarageFloor.jsx so three.js never weighs down the dashboard.
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'
import { buildVehicle, paintFor } from '../vehicle3d/models.js'
import { BAYS, FLOOR, STATIONS } from './layout.js'

const ACCENT = 0xff5b1f
const INK = '#1b1b1d'
const MUTED = '#8a8883'
const TARGET = new THREE.Vector3(0, 0.3, 0.6)
const IDLE_MS = 6000

const mat = {
  floor: new THREE.MeshStandardMaterial({ color: 0xeceae5, roughness: 0.92 }),
  wall: new THREE.MeshStandardMaterial({ color: 0xf7f6f3, roughness: 0.95 }),
  wallEdge: new THREE.MeshStandardMaterial({ color: 0xdedbd4, roughness: 0.9 }),
  lift: new THREE.MeshStandardMaterial({ color: 0x3b3e44, metalness: 0.6, roughness: 0.45 }),
  liftTop: new THREE.MeshStandardMaterial({ color: 0x8b9099, metalness: 0.7, roughness: 0.35 }),
  steel: new THREE.MeshStandardMaterial({ color: 0xc9cdd3, metalness: 0.85, roughness: 0.3 }),
  cart: new THREE.MeshStandardMaterial({ color: 0xc8312b, metalness: 0.3, roughness: 0.45 }),
  rubber: new THREE.MeshStandardMaterial({ color: 0x1d1d1f, roughness: 0.9 }),
  shelf: new THREE.MeshStandardMaterial({ color: 0x9aa0a8, metalness: 0.5, roughness: 0.5 }),
  box: new THREE.MeshStandardMaterial({ color: 0xd9c7a3, roughness: 0.85 }),
  water: new THREE.MeshStandardMaterial({ color: 0x9fd3ff, transparent: true, opacity: 0.35, roughness: 0.1 }),
  overall: new THREE.MeshStandardMaterial({ color: 0x2f4f8f, roughness: 0.7 }),
  skin: new THREE.MeshStandardMaterial({ color: 0xc68e60, roughness: 0.6 }),
  cap: new THREE.MeshStandardMaterial({ color: ACCENT, roughness: 0.6 }),
  shoe: new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.8 }),
}

function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  draw(c.getContext('2d'), w, h)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 8
  return tex
}

// Text painted flat on the floor (station names, bay numbers)
function floorText(text, { size = 0.6, color = INK, weight = 700, font = 'Inter, system-ui, sans-serif', width = 6 } = {}) {
  const px = 128
  const tex = canvasTexture(Math.round((width / size) * px), px, (g, w, h) => {
    g.fillStyle = color
    g.font = `${weight} ${Math.round(h * 0.62)}px ${font}`
    g.textBaseline = 'middle'
    g.fillText(text, 4, h / 2)
  })
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, size), new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }))
  mesh.rotation.x = -Math.PI / 2
  mesh.position.y = 0.006
  return mesh
}

// A thin painted line on the floor between two points
function floorLine(x0, z0, x1, z1, color = 0xc9c5bc, width = 0.06) {
  const len = Math.hypot(x1 - x0, z1 - z0)
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(len, width), new THREE.MeshBasicMaterial({ color }))
  mesh.rotation.x = -Math.PI / 2
  mesh.rotation.z = -Math.atan2(z1 - z0, x1 - x0)
  mesh.position.set((x0 + x1) / 2, 0.004, (z0 + z1) / 2)
  return mesh
}

function rect(group, x0, z0, x1, z1, color, width) {
  group.add(floorLine(x0, z0, x1, z0, color, width), floorLine(x1, z0, x1, z1, color, width),
    floorLine(x1, z1, x0, z1, color, width), floorLine(x0, z1, x0, z0, color, width))
}

function box(w, h, d, material, x, y, z, r = 0.02) {
  const mesh = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2, h / 2, d / 2)), material)
  mesh.position.set(x, y, z)
  return mesh
}

function rod(a, b, r, material) {
  const dir = b.clone().sub(a)
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, dir.length(), 12), material)
  mesh.position.copy(a).addScaledVector(dir, 0.5)
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize())
  return mesh
}

// The building: floor, walls, painted stations, equipment. Static.
function buildGarage() {
  const g = new THREE.Group()
  const W = FLOOR.x1 - FLOOR.x0
  const D = FLOOR.z1 - FLOOR.z0
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(W + 6, D + 5), mat.floor)
  floor.rotation.x = -Math.PI / 2
  floor.position.set(0, 0, 1)
  g.add(floor)
  // Fine grid like a blueprint
  const grid = new THREE.GridHelper(W + 6, (W + 6) * 2, 0xdcd9d2, 0xe4e1db)
  grid.position.set(0, 0.002, 1)
  grid.scale.z = (D + 5) / (W + 6)
  g.add(grid)

  // Back wall and the two side walls (low, so the camera sees over them), with openings for the doors
  g.add(box(W + 0.4, 2.6, 0.25, mat.wall, 0, 1.3, FLOOR.z0 - 0.15, 0.04))
  g.add(box(W + 0.4, 0.12, 0.32, mat.wallEdge, 0, 2.62, FLOOR.z0 - 0.15, 0.03))
  for (const [x, label] of [[FLOOR.x0 - 0.15, 'IN'], [FLOOR.x1 + 0.15, 'OUT']]) {
    g.add(box(0.25, 1.2, 4.2, mat.wall, x, 0.6, FLOOR.z0 + 2.1, 0.04))
    g.add(box(0.25, 1.2, 2.6, mat.wall, x, 0.6, FLOOR.z1 - 1.3, 0.04))
    // Door opening between the wall pieces: arrows on the floor
    const arrow = floorText(label === 'IN' ? '→ IN' : 'OUT →', { size: 0.5, color: ACCENT, width: 2 })
    arrow.position.set(x + (label === 'IN' ? 0.6 : -2.4), 0.007, 1.9)
    g.add(arrow)
  }

  // Stations: outline, name and hint painted on the floor
  for (const s of STATIONS) {
    rect(g, s.x0, FLOOR.z0 + 0.4, s.x1, FLOOR.z1 - 0.2, 0xb9b4aa, 0.05)
    const name = floorText(s.label.toUpperCase(), { size: 0.42, width: 4.4, weight: 700 })
    name.position.set(s.x0 + 2.2 + 0.15, 0.007, FLOOR.z1 + 0.35)
    const hint = floorText(s.hint, { size: 0.3, width: 4.4, weight: 500, color: MUTED })
    hint.position.set(s.x0 + 2.2 + 0.15, 0.007, FLOOR.z1 + 0.8)
    g.add(name, hint)
  }

  // Wash bay: an arch with spray bars and a drain grate
  const wx = -5.9
  for (const z of [-4.2, 4.0]) g.add(rod(new THREE.Vector3(wx, 0, z), new THREE.Vector3(wx, 2.3, z), 0.07, mat.steel))
  g.add(rod(new THREE.Vector3(wx, 2.3, -4.2), new THREE.Vector3(wx, 2.3, 4.0), 0.07, mat.steel))
  for (const z of [-3, -1, 1, 3]) g.add(box(0.5, 0.08, 0.5, mat.steel, wx, 2.22, z))
  g.add(box(3.6, 0.01, 0.3, mat.lift, wx, 0.006, 0, 0.004))
  // Hose reel on the back wall
  const reel = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.07, 10, 28), new THREE.MeshStandardMaterial({ color: 0x2a7de1, roughness: 0.5 }))
  reel.position.set(-7.4, 1.3, FLOOR.z0 + 0.1)
  g.add(reel)

  // Service bays: numbered lifts, a tool cart each, a tyre stack and parts shelves on the back wall
  for (let i = 0; i < BAYS; i++) {
    const x = -1.35 + i * 3.4
    rect(g, x - 1.5, FLOOR.z0 + 0.7, x + 1.5, 2.2, 0xd0ccc3, 0.04)
    const num = floorText(`BAY ${i + 1}`, { size: 0.34, width: 1.6, color: MUTED, font: 'JetBrains Mono, ui-monospace, monospace' })
    num.position.set(x - 0.75, 0.007, 1.85)
    g.add(num)
    g.add(box(2.5, 0.16, 0.95, mat.lift, x, 0.08, -1.2, 0.03))
    g.add(box(2.3, 0.04, 0.8, mat.liftTop, x, 0.18, -1.2, 0.01))
    const cart = new THREE.Group()
    cart.add(box(0.7, 0.75, 0.45, mat.cart, 0, 0.45, 0, 0.04))
    for (let d = 0; d < 3; d++) cart.add(box(0.6, 0.01, 0.02, mat.steel, 0, 0.3 + d * 0.2, 0.23))
    for (const [dx, dz] of [[-0.28, -0.17], [0.28, -0.17], [-0.28, 0.17], [0.28, 0.17]]) {
      const w = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.04, 12), mat.rubber)
      w.rotation.x = Math.PI / 2
      w.position.set(dx, 0.05, dz)
      cart.add(w)
    }
    cart.position.set(x + 1.05, 0, -3.5)
    g.add(cart)
  }
  for (let t = 0; t < 4; t++) {
    const tyre = new THREE.Mesh(new THREE.TorusGeometry(0.28, 0.1, 10, 24), mat.rubber)
    tyre.rotation.x = Math.PI / 2
    tyre.position.set(7.1, 0.1 + t * 0.2, -4.4)
    g.add(tyre)
  }
  const shelves = new THREE.Group()
  for (let level = 0; level < 3; level++) {
    shelves.add(box(3.4, 0.04, 0.5, mat.shelf, 0, 0.45 + level * 0.65, 0))
    for (let b = 0; b < 5; b++) shelves.add(box(0.42, 0.3, 0.36, mat.box, -1.35 + b * 0.68, 0.63 + level * 0.65, 0, 0.02))
  }
  for (const x of [-1.68, 1.68]) shelves.add(box(0.05, 1.9, 0.5, mat.shelf, x, 0.95, 0))
  shelves.position.set(2.05, 0, FLOOR.z0 + 0.35)
  g.add(shelves)

  // Delivery: a pickup line
  g.add(floorLine(8.6, FLOOR.z1 - 0.6, 12.6, FLOOR.z1 - 0.6, ACCENT, 0.08))
  return { group: g, shelves }
}

// A simple car for four-wheelers (the job view has no car model)
function buildCar(paint) {
  const g = new THREE.Group()
  const body = new THREE.MeshPhysicalMaterial({ color: paint, metalness: 0.2, roughness: 0.35, clearcoat: 0.8 })
  const glass = new THREE.MeshStandardMaterial({ color: 0x1e2a36, metalness: 0.3, roughness: 0.15 })
  g.add(box(3.7, 0.62, 1.66, body, 0, 0.62, 0, 0.18))
  g.add(box(2.0, 0.5, 1.48, glass, -0.2, 1.12, 0, 0.18))
  g.add(box(1.9, 0.06, 1.5, body, -0.2, 1.38, 0, 0.03))
  for (const [x, z] of [[1.25, 0.78], [1.25, -0.78], [-1.2, 0.78], [-1.2, -0.78]]) {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.31, 0.31, 0.22, 24), mat.rubber)
    w.rotation.x = Math.PI / 2
    w.position.set(x, 0.31, z)
    g.add(w)
  }
  return { group: g, zones: {} }
}

// A mechanic: overalls, cap in the garage's accent colour
function buildMechanic() {
  const g = new THREE.Group()
  const body = new THREE.Group()
  for (const s of [-1, 1]) {
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.55, 6, 12), mat.overall)
    leg.position.set(0, 0.38, s * 0.1)
    body.add(leg)
    body.add(box(0.22, 0.07, 0.12, mat.shoe, 0.04, 0.04, s * 0.1, 0.03))
  }
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.42, 6, 16), mat.overall)
  torso.position.y = 1.05
  torso.scale.z = 0.8
  body.add(torso)
  const arms = []
  for (const s of [-1, 1]) {
    const arm = new THREE.Group()
    const a = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.5, 6, 12), mat.overall)
    a.position.y = -0.3
    arm.add(a)
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.065, 12, 10), mat.skin)
    hand.position.y = -0.62
    arm.add(hand)
    arm.position.set(0, 1.32, s * 0.27)
    body.add(arm)
    arms.push(arm)
  }
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 16), mat.skin)
  head.position.y = 1.58
  body.add(head)
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.155, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2), mat.cap)
  cap.position.y = 1.6
  body.add(cap)
  body.add(box(0.14, 0.02, 0.2, mat.cap, 0.14, 1.6, 0, 0.01))
  g.add(body)
  return { group: g, body, arms }
}

function radialTexture(stops) {
  return canvasTexture(128, 128, (g) => {
    const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
    for (const [at, color] of stops) grad.addColorStop(at, color)
    g.fillStyle = grad
    g.fillRect(0, 0, 128, 128)
  })
}

const rand = (a, b) => a + Math.random() * (b - a)

export function createGarage(canvas, { onSelect, onFrame, reducedMotion = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.outputColorSpace = THREE.SRGBColorSpace

  const scene = new THREE.Scene()
  const pmrem = new THREE.PMREMGenerator(renderer)
  const envRT = pmrem.fromScene(new RoomEnvironment(), 0.04)
  scene.environment = envRT.texture
  scene.environmentIntensity = 0.55
  scene.add(new THREE.HemisphereLight(0xffffff, 0x9a958c, 0.9))
  const sun = new THREE.DirectionalLight(0xffffff, 1.5)
  sun.position.set(-6, 14, 8)
  scene.add(sun)

  const camera = new THREE.PerspectiveCamera(30, 1, 0.5, 200)

  const garage = buildGarage()
  scene.add(garage.group)

  // Soft shadow blob under vehicles and people (cheap, phone friendly)
  const blob = radialTexture([[0, 'rgba(0,0,0,0.35)'], [0.6, 'rgba(0,0,0,0.12)'], [1, 'rgba(0,0,0,0)']])
  const blobMat = new THREE.MeshBasicMaterial({ map: blob, transparent: true, depthWrite: false })
  const ringTex = radialTexture([[0, 'rgba(255,255,255,0)'], [0.62, 'rgba(255,255,255,0)'], [0.7, 'rgba(255,255,255,1)'],
    [0.78, 'rgba(255,255,255,0)'], [1, 'rgba(255,255,255,0)']])

  const controls = new OrbitControls(camera, canvas)
  controls.target.copy(TARGET)
  controls.enableDamping = true
  controls.enablePan = false
  controls.minDistance = 7
  controls.maxDistance = 42
  controls.minPolarAngle = 0.35
  controls.maxPolarAngle = 1.15
  controls.minAzimuthAngle = -0.9
  controls.maxAzimuthAngle = 0.9
  let lastTouch = -Infinity
  controls.addEventListener('start', () => { lastTouch = performance.now() })
  controls.addEventListener('end', () => { lastTouch = performance.now() })
  controls.update()

  // Water at the wash bay
  const drops = 500
  const waterGeo = new THREE.BufferGeometry()
  waterGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(drops * 3), 3))
  const water = new THREE.Points(waterGeo, new THREE.PointsMaterial({ size: 0.06, color: 0x4aa8ff, map: radialTexture([[0, 'rgba(255,255,255,1)'], [1, 'rgba(255,255,255,0)']]), transparent: true, depthWrite: false }))
  water.frustumCulled = false
  water.visible = false
  scene.add(water)
  const dropVel = new Float32Array(drops)
  let washZ = []

  const vehicles = new Map() // job id -> { group, target, ring, alert, leaving }
  const people = new Map() // mechanic name -> { group, body, arms, target, busy, phase }
  let selected = null
  let lowStock = false
  let active = true
  let frame = 0
  let last = performance.now()
  let time = 0
  const tmp = new THREE.Vector3()

  function addVehicle(v) {
    const built = v.kind === 'car' ? buildCar(paintFor('motorcycle', v.plate)) : buildVehicle(v.kind, { paint: paintFor(v.kind, v.plate), plate: v.plate })
    const group = new THREE.Group()
    group.add(built.group)
    built.group.traverse((o) => { if (o.isMesh) o.userData.jobId = v.id })
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(v.kind === 'car' ? 4.4 : 2.6, v.kind === 'car' ? 2.2 : 1.1), blobMat)
    shadow.rotation.x = -Math.PI / 2
    shadow.position.y = 0.01
    group.add(shadow)
    const ring = new THREE.Mesh(new THREE.PlaneGeometry(3.2, 3.2), new THREE.MeshBasicMaterial({ map: ringTex, color: ACCENT, transparent: true, depthWrite: false, opacity: 0 }))
    ring.rotation.x = -Math.PI / 2
    ring.position.y = 0.02
    group.add(ring)
    // New jobs drive in through the front door
    group.position.set(FLOOR.x0 - 3, 0, 1.9)
    scene.add(group)
    const entry = { group, ring, target: new THREE.Vector3(), lift: 0, alert: null, leaving: false }
    vehicles.set(v.id, entry)
    return entry
  }

  function addPerson(name) {
    const p = buildMechanic()
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.9), blobMat)
    shadow.rotation.x = -Math.PI / 2
    shadow.position.y = 0.012
    p.group.add(shadow)
    p.group.position.set(FLOOR.x0 + 1, 0, FLOOR.z1 - 1)
    p.group.traverse((o) => { if (o.isMesh) o.userData.person = name })
    scene.add(p.group)
    const entry = { ...p, target: new THREE.Vector3(), busy: false, phase: rand(0, 6) }
    people.set(name, entry)
    return entry
  }

  function update(plan, { low = false } = {}) {
    lowStock = low
    const seen = new Set()
    for (const v of plan.vehicles) {
      seen.add(v.id)
      const e = vehicles.get(v.id) || addVehicle(v)
      e.leaving = false
      e.target.set(v.x, 0, v.z)
      e.lift = v.station === 'service' && v.slot < BAYS ? 0.2 : 0 // on the lift
      e.alert = v.alert
      e.station = v.station
    }
    for (const [id, e] of vehicles) {
      if (!seen.has(id) && !e.leaving) {
        e.leaving = true // delivered: drive out through the exit
        e.target.set(FLOOR.x1 + 4, 0, 1.9)
      }
    }
    const names = new Set()
    for (const m of plan.mechanics) {
      names.add(m.name)
      const p = people.get(m.name) || addPerson(m.name)
      p.target.set(m.x, 0, m.z)
      p.busy = m.busy
      p.jobId = m.jobId
    }
    for (const [name, p] of people) {
      if (!names.has(name)) {
        // Not on a vehicle right now: wait by the parts shelves
        const i = [...people.keys()].indexOf(name)
        p.target.set(0.6 + i * 0.7, 0, FLOOR.z0 + 1.3)
        p.busy = false
        p.jobId = null
      }
    }
    washZ = plan.vehicles.filter((v) => v.station === 'wash').map((v) => v.z)
    water.visible = washZ.length > 0
    if (reducedMotion) snap()
  }

  // Jump straight to the targets (first frame, reduced motion)
  function snap() {
    for (const e of vehicles.values()) e.group.position.copy(e.target).setY(e.lift)
    for (const p of people.values()) p.group.position.copy(p.target)
  }

  function select(id) {
    selected = id
  }

  function step(dt) {
    time += dt
    const pulse = 0.5 + 0.5 * Math.sin(time * 4.5)
    for (const [id, e] of vehicles) {
      const pos = e.group.position
      const k = Math.min(1, dt * (e.leaving ? 1.2 : 1.6))
      const dx = e.target.x - pos.x
      const dz = e.target.z - pos.z
      const moving = Math.hypot(dx, dz) > 0.05
      pos.x += dx * k
      pos.z += dz * k
      pos.y += ((moving ? 0 : e.lift) - pos.y) * Math.min(1, dt * 3)
      // Face the way it's moving, settle facing forward (+x)
      const want = moving && Math.hypot(dx, dz) > 0.6 ? -Math.atan2(dz, dx) * 0.5 : 0
      e.group.rotation.y += (want - e.group.rotation.y) * Math.min(1, dt * 3)
      const ringOn = id === selected ? 0.95 : e.alert === 'approval' ? 0.35 + pulse * 0.6 : 0
      e.ring.material.opacity += (ringOn - e.ring.material.opacity) * Math.min(1, dt * 6)
      e.ring.material.color.set(id === selected ? ACCENT : 0xffa000)
      if (e.leaving && pos.x > FLOOR.x1 + 3.5) {
        scene.remove(e.group)
        e.group.traverse((o) => { o.geometry?.dispose() })
        vehicles.delete(id)
      }
    }
    for (const p of people.values()) {
      const pos = p.group.position
      const dx = p.target.x - pos.x
      const dz = p.target.z - pos.z
      const dist = Math.hypot(dx, dz)
      const walking = dist > 0.08
      const k = Math.min(1, (dt * 2.8) / Math.max(dist, 0.001))
      pos.x += dx * Math.min(1, k)
      pos.z += dz * Math.min(1, k)
      p.phase += dt * (walking ? 9 : p.busy ? 4 : 1.2)
      // Walk: swing arms; working: one arm busy at the vehicle; idle: breathe
      const facing = walking ? -Math.atan2(dz, dx) : p.jobId && vehicles.get(p.jobId) ? -Math.atan2(vehicles.get(p.jobId).group.position.z - pos.z, vehicles.get(p.jobId).group.position.x - pos.x) : Math.PI / 2
      p.group.rotation.y += Math.atan2(Math.sin(facing - p.group.rotation.y), Math.cos(facing - p.group.rotation.y)) * Math.min(1, dt * 5)
      p.arms[0].rotation.z = walking ? Math.sin(p.phase) * 0.5 : p.busy ? -0.9 + Math.sin(p.phase) * 0.35 : 0
      p.arms[1].rotation.z = walking ? -Math.sin(p.phase) * 0.5 : 0
      p.body.position.y = walking ? Math.abs(Math.sin(p.phase)) * 0.04 : Math.sin(p.phase) * 0.008
    }
    // Parts shelves glow when stock is low
    mat.box.emissive.set(lowStock ? ACCENT : 0x000000)
    mat.box.emissiveIntensity = lowStock ? 0.15 + pulse * 0.35 : 0

    if (water.visible) {
      const pos = water.geometry.attributes.position.array
      for (let i = 0; i < drops; i++) {
        if (pos[i * 3 + 1] <= 0.05) {
          pos[i * 3] = -5.9 + rand(-0.9, 0.9)
          pos[i * 3 + 1] = rand(1.6, 2.2)
          pos[i * 3 + 2] = washZ[i % washZ.length] + rand(-0.5, 0.5)
          dropVel[i] = rand(2.5, 4)
        }
        pos[i * 3 + 1] -= dropVel[i] * dt
      }
      water.geometry.attributes.position.needsUpdate = true
    }

    // Idle camera: a slow sway so the floor feels alive
    if (!reducedMotion && performance.now() - lastTouch > IDLE_MS) {
      const sph = new THREE.Spherical().setFromVector3(tmp.copy(camera.position).sub(controls.target))
      sph.theta += (baseTheta + 0.12 * Math.sin(time * 0.15) - sph.theta) * Math.min(1, dt * 0.8)
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

  // Click a vehicle (or a mechanic) to select its job
  const ray = new THREE.Raycaster()
  let down = null
  canvas.addEventListener('pointerdown', (e) => { down = [e.clientX, e.clientY] })
  canvas.addEventListener('pointerup', (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return
    const r = canvas.getBoundingClientRect()
    ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera)
    const targets = [...[...vehicles.values()].map((v) => v.group), ...[...people.values()].map((p) => p.group)]
    const hit = ray.intersectObjects(targets, true).find((h) => h.object.userData.jobId || h.object.userData.person)
    const id = hit?.object.userData.jobId || (hit && people.get(hit.object.userData.person)?.jobId) || null
    onSelect?.(id)
  })

  // Screen positions for the HTML labels: vehicles (plate chip) and mechanics (name tag)
  function labels() {
    const el = renderer.domElement
    const out = []
    const project = (v, key, kind) => {
      tmp.copy(v).project(camera)
      if (tmp.z < 1) out.push({ key, kind, x: ((tmp.x + 1) / 2) * el.clientWidth, y: ((1 - tmp.y) / 2) * el.clientHeight })
    }
    for (const [id, e] of vehicles) if (!e.leaving) project(tmp.set(0, 0, 0).add(e.group.position).setY(e.group.position.y + 1.45), id, 'vehicle')
    for (const [name, p] of people) project(tmp.copy(p.group.position).setY(2.0), name, 'person')
    return out
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

  // Landscape: the garage seen from the front, door on the left. Portrait (phones): seen from the delivery end,
  // so the long floor runs up the screen. Then step back until the floor's width fits the frame.
  let portrait = null
  let baseTheta = 0.03
  function fit() {
    const nowPortrait = camera.aspect < 1.1
    if (nowPortrait !== portrait) {
      portrait = nowPortrait
      baseTheta = portrait ? Math.PI / 2 : 0.03
      controls.minAzimuthAngle = baseTheta - 0.9
      controls.maxAzimuthAngle = baseTheta + 0.9
      camera.position.copy(controls.target).add(tmp.setFromSpherical(new THREE.Spherical(20, portrait ? 0.62 : 0.78, baseTheta)))
    }
    const halfW = portrait ? (FLOOR.z1 - FLOOR.z0) / 2 + 1.4 : (FLOOR.x1 - FLOOR.x0) / 2 + 0.6
    const hfov = 2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * camera.aspect)
    const dist = Math.max(10, (halfW / Math.tan(hfov / 2)) * (portrait ? 1.0 : 1.13))
    const dir = tmp.copy(camera.position).sub(controls.target).normalize()
    camera.position.copy(controls.target).addScaledVector(dir, dist)
    controls.maxDistance = dist * 1.4
    controls.update()
  }

  function resize(w, h) {
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.fov = w / h < 1.1 ? 50 : 34
    camera.updateProjectionMatrix()
    fit()
    render()
  }

  // Frame one station (from the side panel)
  function focus(key) {
    const s = STATIONS.find((st) => st.key === key)
    const x = s ? (s.x0 + s.x1) / 2 : 0
    controls.target.set(x * 0.6, 0, 0.4)
    lastTouch = performance.now()
  }

  function dispose() {
    cancelAnimationFrame(frame)
    controls.dispose()
    scene.traverse((o) => {
      o.geometry?.dispose()
      const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : []
      for (const m of mats) { m.map?.dispose() }
    })
    envRT.dispose()
    pmrem.dispose()
    renderer.dispose()
  }

  let first = true
  const api = {
    update(plan, opts) {
      update(plan, opts)
      if (first) {
        first = false
        snap() // open on the garage as it is, not with everyone driving in
      }
    },
    select, resize, setActive, labels, focus, dispose,
    // For debugging in dev tools: where everyone is
    debug: () => ({ vehicles: [...vehicles].map(([id, e]) => [id, e.group.position.toArray()]),
      people: [...people].map(([n, p]) => [n, p.group.position.toArray(), p.target.toArray(), p.jobId]) }),
  }
  loop()
  return api
}
