// A commuter motorcycle and a scooter, built from three.js primitives (no model files, nothing to license).
// Axes: x = forward, y = up, z = the vehicle's right side. Units are metres, wheels touch y = 0.
// Every serviceable part is registered in a zone ("clutch", "brakes", "chain"...) so the scene can light
// up exactly that part. Zone names match src/vehicle3d/focus.js.
import * as THREE from 'three'
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js'

const V = (x, y, z = 0) => new THREE.Vector3(x, y, z)
const UP = V(0, 1, 0)

const PAINTS = {
  motorcycle: [0xb3121e, 0x1f4fd1, 0x17181b, 0x5d6470, 0xd9dde3],
  scooter: [0x8a1c24, 0x0f766e, 0xe8e6e1, 0x22408f, 0x4b4f58],
}

// Same plate -> same colour, so a customer's bike looks the same every visit.
export function paintFor(kind, plate = '') {
  let h = 0
  for (const c of plate) h = (h * 31 + c.charCodeAt(0)) >>> 0
  const list = PAINTS[kind] || PAINTS.motorcycle
  return list[h % list.length]
}

function materials(paint) {
  const light = new THREE.Color(paint).getHSL({}).l > 0.6
  return {
    paint: new THREE.MeshPhysicalMaterial({ color: paint, metalness: 0.15, roughness: 0.38, clearcoat: 0.8, clearcoatRoughness: 0.18 }),
    trim: new THREE.MeshStandardMaterial({ color: light ? 0x2b2d31 : 0x0f1012, metalness: 0.3, roughness: 0.55 }),
    rubber: new THREE.MeshStandardMaterial({ color: 0x1a1a1c, roughness: 0.92 }),
    chrome: new THREE.MeshStandardMaterial({ color: 0xf2f3f7, metalness: 1, roughness: 0.12 }),
    alloy: new THREE.MeshStandardMaterial({ color: 0xb9bec6, metalness: 0.85, roughness: 0.3 }),
    dark: new THREE.MeshStandardMaterial({ color: 0x3b3e44, metalness: 0.75, roughness: 0.4 }),
    black: new THREE.MeshStandardMaterial({ color: 0x141416, metalness: 0.25, roughness: 0.6 }),
    seat: new THREE.MeshStandardMaterial({ color: 0x1b1b1e, roughness: 0.78 }),
    lens: new THREE.MeshStandardMaterial({ color: 0xfff7e6, emissive: 0xfff0c8, emissiveIntensity: 0.9, roughness: 0.08 }),
    red: new THREE.MeshStandardMaterial({ color: 0xc0121c, emissive: 0x8a0010, emissiveIntensity: 0.7, roughness: 0.25 }),
    amber: new THREE.MeshStandardMaterial({ color: 0xffa51f, emissive: 0xc06000, emissiveIntensity: 0.5, roughness: 0.25 }),
    spring: new THREE.MeshStandardMaterial({ color: 0xd8262e, metalness: 0.5, roughness: 0.35 }),
    ceramic: new THREE.MeshStandardMaterial({ color: 0xf1f1ee, roughness: 0.4 }),
  }
}

// Collects meshes and zones while a model is built.
class Kit {
  constructor(paint) {
    this.group = new THREE.Group()
    this.m = materials(paint)
    this.zones = {}
  }

  add(mesh, zone, anchor) {
    this.group.add(mesh)
    if (zone) {
      mesh.material = mesh.material.clone() // own material, so lighting it up touches nothing else
      const z = (this.zones[zone] ||= { meshes: [], anchor: null })
      z.meshes.push(mesh)
      if (anchor) z.anchor = anchor
    }
    return mesh
  }

  rod(a, b, r, mat, zone, segs = 14) {
    const dir = b.clone().sub(a)
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, dir.length(), segs), mat)
    mesh.position.copy(a).addScaledVector(dir, 0.5)
    mesh.quaternion.setFromUnitVectors(UP, dir.normalize())
    return this.add(mesh, zone)
  }

  tube(points, r, mat, zone, closed = false, segs = 64) {
    const curve = new THREE.CatmullRomCurve3(points, closed, 'centripetal')
    return this.add(new THREE.Mesh(new THREE.TubeGeometry(curve, segs, r, 10, closed), mat), zone)
  }

  box(w, h, d, radius, mat, at, zone, rotZ = 0) {
    const mesh = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 4, Math.min(radius, w / 2, h / 2, d / 2)), mat)
    mesh.position.copy(at)
    mesh.rotation.z = rotZ
    return this.add(mesh, zone)
  }

  // A flat disc facing sideways (axis along z), e.g. a clutch cover or a sprocket.
  disc(r, thick, mat, at, zone, segs = 40) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r, r, thick, segs), mat)
    mesh.rotation.x = Math.PI / 2
    mesh.position.copy(at)
    return this.add(mesh, zone)
  }

  // A disc facing forward (axis along x), e.g. a headlight or horn.
  front(r, thick, mat, at, zone, r2 = r) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r2, r, thick, 36), mat)
    mesh.rotation.z = -Math.PI / 2
    mesh.position.copy(at)
    return this.add(mesh, zone)
  }

  ball(r, mat, at, zone, scale = [1, 1, 1]) {
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 20), mat)
    mesh.scale.set(...scale)
    mesh.position.copy(at)
    return this.add(mesh, zone)
  }

  // Curved mudguard band around a wheel. theta: 0.5*PI = front, PI = top, 1.5*PI = back.
  fender(center, radius, width, from, to, mat) {
    const g = new THREE.CylinderGeometry(radius, radius, width, 40, 1, true, from * Math.PI, (to - from) * Math.PI)
    const mesh = new THREE.Mesh(g, mat.clone())
    mesh.material.side = THREE.DoubleSide
    mesh.rotation.x = Math.PI / 2
    mesh.position.copy(center)
    return this.add(mesh)
  }

  // Smooth side-profile panel (a closed outline in x/y) extruded across the vehicle's width.
  panel(outline, width, mat, zone, z = 0) {
    const shape = new THREE.Shape()
    shape.moveTo(...outline[0])
    shape.splineThru(outline.slice(1).concat([outline[0]]).map(([x, y]) => new THREE.Vector2(x, y)))
    const bevel = Math.min(0.035, width / 4)
    const g = new THREE.ExtrudeGeometry(shape, {
      depth: width - 2 * bevel, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 5, curveSegments: 48,
    })
    g.translate(0, 0, -(width - 2 * bevel) / 2 + z)
    return this.add(new THREE.Mesh(g, mat), zone)
  }

  spring(a, b, coil, wire, mat, zone, turns = 9) {
    const len = a.distanceTo(b)
    const pts = []
    for (let i = 0; i <= turns * 24; i++) {
      const t = i / (turns * 24)
      pts.push(V(Math.cos(t * turns * Math.PI * 2) * coil, t * len - len / 2, Math.sin(t * turns * Math.PI * 2) * coil))
    }
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), turns * 24, wire, 6), mat)
    const dir = b.clone().sub(a)
    mesh.position.copy(a).addScaledVector(dir, 0.5)
    mesh.quaternion.setFromUnitVectors(UP, dir.normalize())
    return this.add(mesh, zone)
  }

  wheel(center, R, tyre, style, brakeSide = 1) {
    const { m } = this
    const tyreMesh = new THREE.Mesh(new THREE.TorusGeometry(R - tyre, tyre, 20, 72), m.rubber)
    tyreMesh.position.copy(center)
    tyreMesh.scale.z = 1.15
    this.add(tyreMesh, 'tyres')
    const rimR = R - 2 * tyre - 0.004
    const rim = new THREE.Mesh(new THREE.TorusGeometry(rimR, 0.016, 10, 72), style === 'spoke' ? m.chrome : m.alloy)
    rim.position.copy(center)
    this.add(rim)
    this.disc(0.045, 0.12, m.alloy, center)
    if (style === 'spoke') {
      for (let i = 0; i < 18; i++) {
        const a = (i / 18) * Math.PI * 2
        const side = i % 2 ? 1 : -1
        const hub = center.clone().add(V(Math.cos(a + 0.35 * side) * 0.035, Math.sin(a + 0.35 * side) * 0.035, side * 0.045))
        const out = center.clone().add(V(Math.cos(a) * rimR, Math.sin(a) * rimR, side * 0.006))
        this.rod(hub, out, 0.0028, m.chrome, null, 5)
      }
    } else {
      for (let i = 0; i < 5; i++) {
        const a = (i / 5) * Math.PI * 2 + 0.3
        const p = (r) => center.clone().add(V(Math.cos(a) * r, Math.sin(a) * r, 0))
        this.rod(p(0.04), p(rimR - 0.008), 0.016, m.alloy, null, 8)
      }
    }
    // Drum brake on one side of the hub
    this.disc(R * 0.3, 0.045, m.dark, center.clone().add(V(0, 0, brakeSide * 0.065)), 'brakes')
  }

  // Default anchor of a zone: the centre of its first mesh.
  finish() {
    this.group.updateMatrixWorld(true)
    for (const z of Object.values(this.zones)) {
      if (!z.anchor) z.anchor = new THREE.Box3().setFromObject(z.meshes[0]).getCenter(V(0, 0))
    }
    return { group: this.group, zones: this.zones }
  }
}

function plateTexture(text) {
  const c = document.createElement('canvas')
  c.width = 256
  c.height = 128
  const g = c.getContext('2d')
  g.fillStyle = '#fbfbf7'
  g.fillRect(0, 0, 256, 128)
  g.strokeStyle = '#111'
  g.lineWidth = 6
  g.strokeRect(5, 5, 246, 118)
  g.fillStyle = '#111'
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  const [a, b] = splitPlate(text)
  g.font = 'bold 44px ui-monospace, Menlo, monospace'
  g.fillText(a, 128, 44)
  g.fillText(b, 128, 92)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

// "MH12AB1234" -> ["MH 12", "AB 1234"] (two-line Indian rear plate)
function splitPlate(text = '') {
  const m = text.replace(/\s/g, '').toUpperCase().match(/^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$/)
  return m ? [`${m[1]} ${m[2]}`, `${m[3]} ${m[4]}`.trim()] : [text.slice(0, 5), text.slice(5)]
}

function numberPlate(kit, at, plate, w = 0.2, h = 0.1) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: plateTexture(plate), roughness: 0.5 }))
  mesh.rotation.y = -Math.PI / 2
  mesh.position.copy(at)
  kit.add(mesh)
}

// ------------------------------------------------------------------ motorcycle (Splendor-class commuter)

export function buildMotorcycle({ paint, plate }) {
  const k = new Kit(paint)
  const { m } = k
  const R = 0.31
  const F = V(0.64, R)
  const B = V(-0.62, R)

  k.wheel(F, R, 0.05, 'spoke', 1)
  k.wheel(B, R, 0.055, 'spoke', 1)
  k.zones.tyres.anchor = F.clone().add(V(0.12, R - 0.02))
  k.zones.brakes.anchor = F.clone().add(V(0, 0, 0.07))
  k.fender(F, R + 0.035, 0.1, 0.64, 1.18, m.paint)
  k.fender(B, R + 0.04, 0.13, 0.9, 1.5, m.paint)

  // Front fork and steering
  for (const s of [-1, 1]) {
    k.rod(V(0.64, 0.33, s * 0.085), V(0.565, 0.6, s * 0.085), 0.026, m.alloy, 'suspension')
    k.rod(V(0.565, 0.6, s * 0.085), V(0.47, 0.9, s * 0.085), 0.019, m.chrome)
  }
  k.box(0.07, 0.03, 0.24, 0.01, m.dark, V(0.47, 0.885, 0))
  k.box(0.06, 0.025, 0.22, 0.01, m.dark, V(0.455, 0.955, 0))

  // Headlight, cowl, speedo, horn, indicators
  k.front(0.088, 0.11, m.black, V(0.56, 0.9, 0), null, 0.072)
  k.front(0.074, 0.012, m.lens, V(0.618, 0.9, 0), 'lights')
  k.box(0.12, 0.07, 0.2, 0.03, m.paint, V(0.53, 0.985, 0), null, 0.35)
  const speedo = k.disc(0.045, 0.03, m.black, V(0.475, 1.02, 0))
  speedo.rotation.set(0, 0, 0.9)
  k.front(0.034, 0.03, m.dark, V(0.63, 0.72, 0), 'horn')
  for (const s of [-1, 1]) {
    k.rod(V(0.53, 0.86, s * 0.1), V(0.56, 0.86, s * 0.16), 0.006, m.black)
    k.ball(0.022, m.amber, V(0.565, 0.86, s * 0.165), 'lights', [1.3, 1, 1])
  }

  // Handlebar, grips, levers, mirrors
  k.tube([V(0.42, 1.0, -0.34), V(0.44, 0.985, -0.16), V(0.45, 0.975, 0), V(0.44, 0.985, 0.16), V(0.42, 1.0, 0.34)], 0.012, m.chrome)
  for (const s of [-1, 1]) {
    k.rod(V(0.42, 1.0, s * 0.26), V(0.415, 1.0, s * 0.37), 0.019, m.black)
    k.tube([V(0.44, 1.0, s * 0.2), V(0.47, 1.005, s * 0.26), V(0.455, 1.005, s * 0.34)], 0.006, m.alloy, s < 0 ? 'clutch' : 'brakes')
    k.rod(V(0.43, 1.0, s * 0.2), V(0.39, 1.19, s * 0.26), 0.006, m.chrome, 'mirrors')
    k.ball(0.04, m.black, V(0.385, 1.21, s * 0.27), 'mirrors', [0.3, 0.75, 1.1])
  }

  // Cables: clutch (left) and throttle (right) into the engine
  k.tube([V(0.44, 0.995, -0.22), V(0.5, 0.92, -0.17), V(0.4, 0.68, -0.15), V(0.2, 0.46, -0.13)], 0.006, m.black, 'cables')
  k.tube([V(0.44, 0.995, 0.22), V(0.5, 0.92, 0.16), V(0.32, 0.72, 0.1), V(0.08, 0.56, 0.05)], 0.006, m.black, 'cables')

  // Frame
  k.tube([V(0.47, 0.9), V(0.3, 0.845), V(0.05, 0.785), V(-0.25, 0.745), V(-0.62, 0.765)], 0.021, m.black)
  k.tube([V(0.46, 0.86), V(0.36, 0.66), V(0.27, 0.5)], 0.023, m.black)
  k.tube([V(-0.05, 0.78), V(-0.08, 0.6), V(-0.04, 0.42)], 0.02, m.black)

  // Fuel tank with cap, side panels (battery on the right, air filter on the left)
  k.ball(1, m.paint, V(0.22, 0.875, 0), null, [0.26, 0.115, 0.155])
  k.disc(0.022, 0.012, m.chrome, V(0.21, 0.99, 0)).rotation.set(0, 0, 0)
  k.panel([[-0.06, 0.58], [-0.08, 0.72], [-0.3, 0.73], [-0.28, 0.6]], 0.02, m.paint, 'battery', 0.135)
  k.panel([[-0.06, 0.58], [-0.08, 0.72], [-0.3, 0.73], [-0.28, 0.6]], 0.02, m.paint, 'air_filter', -0.135)
  k.box(0.12, 0.1, 0.06, 0.01, m.black, V(-0.17, 0.64, 0.08))
  k.box(0.15, 0.1, 0.08, 0.02, m.black, V(-0.17, 0.64, -0.06))

  // Engine: crankcase, finned cylinder, covers, plug, carburettor
  k.box(0.36, 0.22, 0.22, 0.05, m.alloy, V(0.07, 0.41, 0), 'engine')
  const axisA = V(0.17, 0.46)
  const axisB = V(0.37, 0.535)
  k.rod(axisA, axisB, 0.052, m.alloy, 'engine')
  for (let i = 0; i <= 6; i++) {
    const p = axisA.clone().lerp(axisB, 0.12 + i * 0.13)
    const fin = new THREE.Mesh(new THREE.CylinderGeometry(0.082, 0.082, 0.011, 28), m.dark)
    fin.position.copy(p)
    fin.quaternion.setFromUnitVectors(UP, axisB.clone().sub(axisA).normalize())
    k.add(fin, 'engine')
  }
  k.disc(0.088, 0.032, m.chrome, V(0.12, 0.41, 0.128), 'clutch')
  k.zones.clutch.anchor = V(0.12, 0.41, 0.15)
  k.disc(0.06, 0.02, m.alloy, V(0.12, 0.41, 0.15), 'clutch')
  k.disc(0.08, 0.03, m.alloy, V(0.04, 0.42, -0.125), 'engine')
  k.rod(V(0.385, 0.545), V(0.42, 0.6), 0.013, m.ceramic, 'spark_plug')
  k.rod(V(0.42, 0.6), V(0.435, 0.625), 0.017, m.black, 'spark_plug')
  k.box(0.08, 0.07, 0.07, 0.015, m.alloy, V(0.05, 0.56, 0), 'carburettor')
  k.rod(V(0.01, 0.57), V(-0.1, 0.62), 0.022, m.black)

  // Chain drive (left side)
  const fs = V(-0.02, 0.37, -0.105)
  const rs = V(B.x, B.y, -0.105)
  k.disc(0.045, 0.012, m.dark, fs, 'chain')
  k.disc(0.1, 0.008, m.dark, rs, 'chain')
  k.tube([V(fs.x, fs.y + 0.05, -0.105), V(fs.x + 0.05, fs.y, -0.105), V(fs.x, fs.y - 0.05, -0.105),
    V(rs.x, rs.y - 0.105, -0.105), V(rs.x - 0.106, rs.y, -0.105), V(rs.x, rs.y + 0.105, -0.105)], 0.009, m.dark, 'chain', true, 120)
  k.zones.chain.anchor = V(-0.32, 0.36, -0.11)

  // Swingarm, rear shocks
  for (const s of [-1, 1]) {
    k.rod(V(-0.03, 0.4, s * 0.09), V(B.x, B.y, s * 0.09), 0.019, m.black)
    k.rod(V(-0.56, 0.33, s * 0.115), V(-0.47, 0.73, s * 0.115), 0.012, m.chrome, 'suspension')
    k.spring(V(-0.545, 0.4, s * 0.115), V(-0.485, 0.66, s * 0.115), 0.03, 0.0055, m.spring, 'suspension')
  }

  // Exhaust (right side)
  k.tube([V(0.37, 0.47, 0.05), V(0.41, 0.36, 0.09), V(0.3, 0.235, 0.125), V(0.02, 0.235, 0.145), V(-0.24, 0.3, 0.165)], 0.022, m.chrome)
  k.rod(V(-0.2, 0.3, 0.17), V(-0.72, 0.43, 0.17), 0.047, m.dark, null, 24)
  k.rod(V(-0.68, 0.42, 0.17), V(-0.74, 0.435, 0.17), 0.05, m.chrome, null, 24)

  // Seat, tail, tail light, grab rail, plate
  k.box(0.6, 0.075, 0.25, 0.035, m.seat, V(-0.23, 0.82, 0), null, 0.035)
  k.ball(1, m.paint, V(-0.6, 0.79, 0), null, [0.24, 0.07, 0.115])
  k.box(0.04, 0.05, 0.11, 0.015, m.red, V(-0.8, 0.795, 0), 'lights')
  k.tube([V(-0.42, 0.84, -0.12), V(-0.68, 0.85, -0.11), V(-0.72, 0.85, 0), V(-0.68, 0.85, 0.11), V(-0.42, 0.84, 0.12)], 0.011, m.chrome)
  for (const s of [-1, 1]) {
    k.rod(V(-0.76, 0.74, s * 0.06), V(-0.78, 0.74, s * 0.14), 0.006, m.black)
    k.ball(0.02, m.amber, V(-0.785, 0.74, s * 0.145), 'lights', [1, 1, 1.3])
  }
  k.rod(V(-0.74, 0.76), V(-0.8, 0.66), 0.01, m.black)
  numberPlate(k, V(-0.805, 0.63, 0), plate)

  // Footpegs
  for (const s of [-1, 1]) k.rod(V(0.0, 0.28, s * 0.1), V(0.0, 0.28, s * 0.23), 0.013, m.black)

  return k.finish()
}

// ------------------------------------------------------------------ scooter (Activa-class)

export function buildScooter({ paint, plate }) {
  const k = new Kit(paint)
  const { m } = k
  const R = 0.255
  const F = V(0.6, R)
  const B = V(-0.6, R)

  k.wheel(F, R, 0.058, 'alloy', 1)
  k.wheel(B, R, 0.062, 'alloy', 1)
  k.zones.tyres.anchor = F.clone().add(V(0.1, R - 0.02))
  k.zones.brakes.anchor = F.clone().add(V(0, 0, 0.07))
  k.fender(F, R + 0.035, 0.12, 0.6, 1.22, m.paint)
  k.fender(B, R + 0.03, 0.15, 0.95, 1.35, m.black)

  // Front suspension and steering column (mostly behind the apron)
  for (const s of [-1, 1]) k.rod(V(0.6, 0.27, s * 0.075), V(0.52, 0.56, s * 0.075), 0.022, m.alloy, 'suspension')
  k.rod(V(0.52, 0.55), V(0.45, 1.02), 0.03, m.dark)

  // Front apron / leg shield, floorboard, rear body
  // Leg shield sweeping down into the floor, as one piece
  k.panel([[0.12, 0.33], [0.36, 0.36], [0.45, 0.47], [0.52, 0.66], [0.565, 0.86], [0.545, 1.0], [0.47, 1.05], [0.41, 0.99],
    [0.375, 0.76], [0.33, 0.55], [0.25, 0.43], [0.14, 0.395]], 0.34, m.paint)
  k.box(0.5, 0.06, 0.31, 0.025, m.paint, V(0.07, 0.33, 0))
  k.box(0.46, 0.012, 0.27, 0.005, m.black, V(0.07, 0.366, 0))
  k.box(0.17, 0.008, 0.15, 0.004, m.dark, V(0.17, 0.375, 0), 'battery')
  k.panel([[-0.2, 0.34], [-0.11, 0.41], [-0.12, 0.6], [-0.21, 0.745], [-0.5, 0.79], [-0.8, 0.775], [-0.925, 0.705],
    [-0.9, 0.615], [-0.76, 0.575], [-0.55, 0.555], [-0.4, 0.47], [-0.3, 0.36]], 0.32, m.paint)
  // Side trim line and a little brand badge, so the body doesn't read as one flat blob
  for (const s of [-1, 1]) k.tube([V(-0.16, 0.5, s * 0.163), V(-0.4, 0.62, s * 0.164), V(-0.8, 0.66, s * 0.158)], 0.006, m.chrome)

  // Handlebar cover with headlight, grips, levers, mirrors, indicators
  k.box(0.13, 0.09, 0.44, 0.04, m.paint, V(0.45, 1.1, 0))
  k.box(0.04, 0.05, 0.2, 0.02, m.lens, V(0.51, 1.1, 0), 'lights')
  k.box(0.035, 0.07, 0.17, 0.02, m.lens, V(0.555, 0.9, 0), 'lights', -0.15)
  for (const s of [-1, 1]) {
    k.rod(V(0.44, 1.1, s * 0.22), V(0.44, 1.1, s * 0.34), 0.019, m.black)
    k.tube([V(0.47, 1.1, s * 0.2), V(0.5, 1.105, s * 0.27), V(0.485, 1.105, s * 0.33)], 0.006, m.alloy, 'brakes')
    k.rod(V(0.45, 1.13, s * 0.17), V(0.42, 1.3, s * 0.22), 0.006, m.chrome, 'mirrors')
    k.ball(0.04, m.black, V(0.415, 1.32, s * 0.23), 'mirrors', [0.3, 0.75, 1.1])
    k.ball(0.022, m.amber, V(0.5, 1.09, s * 0.215), 'lights', [1.3, 1, 1])
    k.ball(0.02, m.amber, V(-0.9, 0.7, s * 0.13), 'lights', [1, 1, 1.4])
  }
  k.tube([V(0.47, 1.08, -0.2), V(0.5, 0.95, -0.14), V(0.52, 0.7, -0.1), V(0.6, 0.35, -0.08)], 0.006, m.black, 'cables')

  // Engine, CVT case with variator cover, air filter (left), shock + exhaust (right)
  k.box(0.18, 0.15, 0.17, 0.04, m.dark, V(-0.08, 0.36, -0.03), 'engine')
  k.box(0.56, 0.15, 0.09, 0.045, m.alloy, V(-0.33, 0.33, -0.125), 'cvt')
  k.disc(0.075, 0.03, m.alloy, V(-0.12, 0.33, -0.175), 'cvt')
  k.disc(0.05, 0.02, m.chrome, V(-0.12, 0.33, -0.19), 'cvt')
  k.box(0.24, 0.09, 0.07, 0.025, m.black, V(-0.4, 0.465, -0.13), 'air_filter')
  k.rod(V(-0.05, 0.43), V(-0.03, 0.49), 0.012, m.ceramic, 'spark_plug')
  k.box(0.07, 0.06, 0.06, 0.015, m.alloy, V(-0.17, 0.45, 0.06), 'carburettor')
  k.rod(V(-0.58, 0.3, 0.12), V(-0.45, 0.56, 0.12), 0.013, m.chrome, 'suspension')
  k.spring(V(-0.565, 0.33, 0.12), V(-0.475, 0.52, 0.12), 0.028, 0.0055, m.spring, 'suspension')
  k.tube([V(-0.06, 0.29, 0.06), V(-0.2, 0.26, 0.12), V(-0.34, 0.3, 0.145)], 0.02, m.dark)
  k.rod(V(-0.32, 0.3, 0.15), V(-0.76, 0.39, 0.15), 0.042, m.dark, null, 24)
  k.rod(V(-0.73, 0.385, 0.15), V(-0.79, 0.4, 0.15), 0.045, m.chrome, null, 24)

  // Seat, tail light, plate
  k.box(0.62, 0.085, 0.29, 0.045, m.seat, V(-0.47, 0.85, 0), null, 0.02)
  k.box(0.04, 0.06, 0.2, 0.02, m.red, V(-0.92, 0.66, 0), 'lights')
  numberPlate(k, V(-0.935, 0.5, 0), plate, 0.18, 0.09)

  return k.finish()
}

export function buildVehicle(kind, opts) {
  return kind === 'scooter' ? buildScooter(opts) : buildMotorcycle(opts)
}
