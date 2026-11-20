// Top-down 3D town: six shops around a snowy plaza, one elf per family member.
// Shop signs start blank ("Shop") and flip to the store's name when an elf heads there.
// Elves wander when idle, walk along the roads, pop inside a shop, and come out carrying a gift.
import * as THREE from "three";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const COLORS = { mom: 0xd6453a, dad: 0x3a78c9, jill: 0x9b59c6, sam: 0x26a065, bill: 0xf08c2e, lucy: 0xef5fa7 };
const WALLS = [0xf6d7a7, 0xbfe0f7, 0xf9c9d1, 0xc9ecc8, 0xe2d4f7, 0xfbe2b8];
const ROOFS = [0xc0392b, 0x2e6fb7, 0xb8457a, 0x2f8f5b, 0x6a4fb3, 0xd07a2a];
const ROAD_Z = 0, ROAD_X = 0, ROAD_W = 5;

const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.85, ...extra });

export class Town {
  constructor(el) {
    this.el = el;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1b2a44);
    this.scene.fog = new THREE.Fog(0x1b2a44, 70, 120);
    const { clientWidth: w, clientHeight: h } = el;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setSize(w, h);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    el.appendChild(this.renderer.domElement);
    this.labels = new CSS2DRenderer();
    this.labels.setSize(w, h);
    Object.assign(this.labels.domElement.style, { position: "absolute", top: "0", left: "0", pointerEvents: "none" });
    el.appendChild(this.labels.domElement);

    // Steep, slightly tilted top-down camera (orthographic so the whole town fits).
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200);
    this.camera.position.set(0, 36, 33);
    this.camera.lookAt(0, 0, 1.5);
    // Drag to orbit, scroll to zoom, within limits that keep the town readable.
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    Object.assign(this.controls, { enableDamping: true, dampingFactor: 0.08, enablePan: false,
      minPolarAngle: 0.25, maxPolarAngle: 1.12, minZoom: 0.8, maxZoom: 2.4, rotateSpeed: 0.6 });
    this.controls.target.set(0, 0, 1.5);
    this.controls.update();
    this.resize();
    addEventListener("resize", () => this.resize());

    this.scene.add(new THREE.HemisphereLight(0xe8f0ff, 0x46557a, 1.25));
    const sun = new THREE.DirectionalLight(0xfff0d8, 1.9);
    sun.position.set(14, 32, 12);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.bias = -0.0005;
    Object.assign(sun.shadow.camera, { left: -34, right: 34, top: 30, bottom: -30 });
    this.scene.add(sun);

    this.shops = {};
    this.elves = {};
    this.onElfClick = null;
    const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
    let down = null;
    this.renderer.domElement.addEventListener("pointerdown", (ev) => (down = [ev.clientX, ev.clientY]));
    this.renderer.domElement.addEventListener("pointerup", (ev) => {
      if (!down || Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 5) return;
      const r = this.renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, this.camera);
      const groups = Object.values(this.elves).map((e) => e.group);
      const hit = ray.intersectObjects(groups, true)[0];
      if (!hit) return;
      let o = hit.object;
      while (o && !o.userData.memberId) o = o.parent;
      if (o && this.onElfClick) this.onElfClick(o.userData.memberId, ev.clientX, ev.clientY);
    });
    this.twinkles = [];
    this.clock = new THREE.Clock();
    this.buildGround();
    this.buildSnow();
    this.animate();
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight, aspect = w / h;
    const view = 19.5;
    Object.assign(this.camera, { left: -view * aspect, right: view * aspect, top: view, bottom: -view });
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.labels.setSize(w, h);
  }

  // ---------------------------------------------------------------- ground, roads, props
  buildGround() {
    const snow = new THREE.Mesh(new THREE.PlaneGeometry(120, 90), mat(0xf1f5fb, { roughness: 1 }));
    snow.rotation.x = -Math.PI / 2;
    snow.receiveShadow = true;
    this.scene.add(snow);

    const flat = (w, d, color, y, x = 0, z = 0) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat(color, { roughness: 0.95 }));
      m.rotation.x = -Math.PI / 2;
      m.position.set(x, y, z);
      m.receiveShadow = true;
      this.scene.add(m);
      return m;
    };
    // sidewalks then asphalt
    flat(110, ROAD_W + 2.4, 0xd7dbe3, 0.01, 0, ROAD_Z);
    flat(ROAD_W + 2.4, 80, 0xd7dbe3, 0.012, ROAD_X, 0);
    flat(110, ROAD_W, 0x5b6170, 0.02, 0, ROAD_Z);
    flat(ROAD_W, 80, 0x5b6170, 0.022, ROAD_X, 0);
    // dashed centre lines
    for (let x = -54; x < 54; x += 3.2) if (Math.abs(x) > 7) flat(1.6, 0.22, 0xffe08a, 0.03, x, ROAD_Z);
    for (let z = -40; z < 40; z += 3.2) if (Math.abs(z) > 7) flat(0.22, 1.6, 0xffe08a, 0.032, ROAD_X, z);
    // crosswalk stripes around the plaza
    for (const [x, z, rot] of [[0, 7.6, 0], [0, -7.6, 0], [7.6, 0, 1], [-7.6, 0, 1]]) {
      for (let i = -2; i <= 2; i++) {
        const s = flat(rot ? 1.6 : 0.55, rot ? 0.55 : 1.6, 0xffffff, 0.035, x + (rot ? 0 : i * 0.95), z + (rot ? i * 0.95 : 0));
        s.material.color.set(0xf4f6fa);
      }
    }
    // plaza with brick ring
    const ring = new THREE.Mesh(new THREE.CylinderGeometry(6.2, 6.2, 0.12, 48), mat(0xb5654a));
    ring.position.y = 0.06;
    ring.receiveShadow = true;
    this.scene.add(ring);
    const plaza = new THREE.Mesh(new THREE.CylinderGeometry(5.6, 5.6, 0.16, 48), mat(0xe9dcc3));
    plaza.position.y = 0.08;
    plaza.receiveShadow = true;
    this.scene.add(plaza);

    this.buildTree();

    // lamp posts at the plaza corners and along the roads
    const lampSpots = [[4.6, 4.6], [-4.6, 4.6], [4.6, -4.6], [-4.6, -4.6], [26, 4], [-26, 4], [26, -4], [-26, -4], [4, 22], [-4, -22]];
    lampSpots.forEach(([x, z], i) => this.lamp(x, z, i < 4));

    // snowy pines + snowmen around the edges
    for (let i = 0; i < 26; i++) {
      const a = (i / 26) * Math.PI * 2;
      const r = 31 + Math.sin(i * 5.3) * 3;
      const x = Math.cos(a) * r * 1.05, z = Math.sin(a) * r * 0.72;
      if (Math.abs(x) < 4 || Math.abs(z) < 4) continue;
      this.pine(x, z, 0.8 + (Math.sin(i * 2.1) + 1) * 0.25);
    }
    [[-9, 18], [9, -18], [24, 15]].forEach(([x, z]) => this.snowman(x, z));
    // little fences in front of shops
    for (const z of [-6.6, 6.6]) for (const x of [-25, -9, 9, 25]) this.fence(x, z);
  }

  buildTree() {
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.4, 1.1, 10), mat(0x7a4b2a));
    trunk.position.y = 0.7;
    tree.add(trunk);
    const tiers = [[2.4, 2.4, 1.9], [1.85, 2.0, 3.1], [1.25, 1.7, 4.15]];
    tiers.forEach(([r, h, y]) => {
      const c = new THREE.Mesh(new THREE.ConeGeometry(r, h, 12), mat(0x1f7a4d));
      c.position.y = y;
      c.castShadow = true;
      tree.add(c);
      const cap = new THREE.Mesh(new THREE.ConeGeometry(r * 0.55, h * 0.35, 12), mat(0xffffff));
      cap.position.y = y + h * 0.36;
      tree.add(cap);
    });
    const colors = [0xff4d4d, 0xffd34d, 0x4dc3ff, 0xff7ae0, 0x7dff8a];
    for (let i = 0; i < 26; i++) {
      const t = i / 26, y = 1.4 + t * 3.4, r = 2.25 * (1 - t * 0.78);
      const a = i * 2.4;
      const b = new THREE.Mesh(new THREE.SphereGeometry(0.14, 8, 6),
        new THREE.MeshStandardMaterial({ color: colors[i % 5], emissive: colors[i % 5], emissiveIntensity: 0.8 }));
      b.position.set(Math.cos(a) * r, y, Math.sin(a) * r);
      tree.add(b);
      this.twinkles.push({ m: b, phase: i * 0.7 });
    }
    const star = new THREE.Mesh(new THREE.OctahedronGeometry(0.45), new THREE.MeshStandardMaterial({ color: 0xffd34d, emissive: 0xffb300, emissiveIntensity: 1.2 }));
    star.position.y = 5.5;
    tree.add(star);
    this.star = star;
    const presents = [[1.6, 0.9, 0xd6453a], [-1.4, 1.2, 0x3a78c9], [0.4, -1.7, 0x26a065], [-1.0, -1.2, 0xf0c419]];
    presents.forEach(([x, z, c]) => {
      const p = this.giftBox(c, 0.7);
      p.position.set(x, 0.5, z);
      tree.add(p);
    });
    this.scene.add(tree);
  }

  giftBox(color, s = 0.5) {
    const g = new THREE.Group();
    const box = new THREE.Mesh(new THREE.BoxGeometry(s, s, s), mat(color));
    box.castShadow = true;
    const r1 = new THREE.Mesh(new THREE.BoxGeometry(s * 1.02, s * 1.02, s * 0.18), mat(0xffe08a));
    const r2 = new THREE.Mesh(new THREE.BoxGeometry(s * 0.18, s * 1.02, s * 1.02), mat(0xffe08a));
    g.add(box, r1, r2);
    return g;
  }

  lamp(x, z, warm) {
    const g = new THREE.Group();
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.1, 2.6, 8), mat(0x2b3242));
    pole.position.y = 1.3;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 10),
      new THREE.MeshStandardMaterial({ color: 0xfff1c1, emissive: 0xffd27a, emissiveIntensity: 1.4 }));
    head.position.y = 2.75;
    g.add(pole, head);
    if (warm) {
      const l = new THREE.PointLight(0xffc56b, 6, 7);
      l.position.y = 2.6;
      g.add(l);
    }
    g.position.set(x, 0, z);
    this.scene.add(g);
  }

  pine(x, z, s) {
    const g = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.18, 0.6, 6), mat(0x6b4226));
    trunk.position.y = 0.3;
    g.add(trunk);
    [[1.1, 1.6, 1.1], [0.8, 1.3, 1.9]].forEach(([r, h, y]) => {
      const c = new THREE.Mesh(new THREE.ConeGeometry(r, h, 8), mat(0x2c7a55));
      c.position.y = y;
      c.castShadow = true;
      g.add(c);
      const cap = new THREE.Mesh(new THREE.ConeGeometry(r * 0.5, h * 0.4, 8), mat(0xffffff));
      cap.position.y = y + h * 0.32;
      g.add(cap);
    });
    g.scale.setScalar(s);
    g.position.set(x, 0, z);
    this.scene.add(g);
  }

  snowman(x, z) {
    const g = new THREE.Group();
    [[0.7, 0.6], [0.5, 1.5], [0.35, 2.2]].forEach(([r, y]) => {
      const b = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 10), mat(0xffffff));
      b.position.y = y;
      b.castShadow = true;
      g.add(b);
    });
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.35, 8), mat(0xff8c1a));
    nose.rotation.x = Math.PI / 2;
    nose.position.set(0, 2.2, 0.4);
    const hat = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 0.4, 12), mat(0x222222));
    hat.position.y = 2.65;
    const scarf = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.08, 6, 16), mat(0xd6453a));
    scarf.rotation.x = Math.PI / 2;
    scarf.position.y = 1.85;
    g.add(nose, hat, scarf);
    g.position.set(x, 0, z);
    this.scene.add(g);
  }

  fence(x, z) {
    const g = new THREE.Group();
    const white = mat(0xffffff);
    for (let i = 0; i < 6; i++) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.6, 0.12), white);
      p.position.set(-1.5 + i * 0.6, 0.3, 0);
      g.add(p);
    }
    const rail = new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.08, 0.06), white);
    rail.position.y = 0.42;
    g.add(rail);
    g.position.set(x - 3, 0, z);
    this.scene.add(g);
  }

  buildSnow() {
    const n = 500, pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 90;
      pos[i * 3 + 1] = Math.random() * 30;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 70;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    this.snow = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.22, transparent: true, opacity: 0.85 }));
    this.scene.add(this.snow);
  }

  // ---------------------------------------------------------------- shops
  setStores(stores) {
    const spots = [[-17, -11.5], [0, -14], [17, -11.5], [-17, 11.5], [0, 14], [17, 11.5]];
    stores.forEach((s, i) => {
      if (this.shops[s.id]) return;
      const [x, z] = spots[i % spots.length];
      const facing = z < 0 ? 1 : -1; // doors face the main road
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      // walls
      const body = new THREE.Mesh(new THREE.BoxGeometry(8, 3.4, 5.6), mat(WALLS[i % 6]));
      body.position.y = 1.7;
      body.castShadow = body.receiveShadow = true;
      g.add(body);
      // gabled roof (triangular prism) with snow on top
      const roofShape = new THREE.Shape();
      roofShape.moveTo(-4.5, 0); roofShape.lineTo(4.5, 0); roofShape.lineTo(0, 2.0); roofShape.lineTo(-4.5, 0);
      const roof = new THREE.Mesh(new THREE.ExtrudeGeometry(roofShape, { depth: 6.2, bevelEnabled: false }), mat(ROOFS[i % 6]));
      roof.position.set(0, 3.4, -3.1);
      roof.castShadow = true;
      g.add(roof);
      const snowCap = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.35, 6.3), mat(0xffffff));
      snowCap.position.set(0, 5.3, 0);
      g.add(snowCap);
      const chimney = new THREE.Mesh(new THREE.BoxGeometry(0.7, 1.4, 0.7), mat(0x9b4a3a));
      chimney.position.set(2.4, 4.6, 1.2);
      chimney.castShadow = true;
      g.add(chimney);
      // glowing windows on the street side
      const winMat = new THREE.MeshStandardMaterial({ color: 0xfff1b8, emissive: 0xffc94d, emissiveIntensity: 0.9 });
      for (const wx of [-2.6, 2.6]) {
        const w = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.1, 0.08), winMat);
        w.position.set(wx, 1.9, facing * 2.82);
        const frame = new THREE.Mesh(new THREE.BoxGeometry(1.7, 1.3, 0.05), mat(0xffffff));
        frame.position.set(wx, 1.9, facing * 2.80);
        g.add(frame, w);
      }
      // door + striped awning
      const door = new THREE.Mesh(new THREE.BoxGeometry(1.3, 2.1, 0.1), mat(0x6b3f22));
      door.position.set(0, 1.05, facing * 2.84);
      g.add(door);
      const stripes = new THREE.Group();
      for (let k = 0; k < 8; k++) {
        const st = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.08, 1.1), mat(k % 2 ? 0xffffff : ROOFS[i % 6]));
        st.position.set(-1.75 + k * 0.5, 0, 0);
        stripes.add(st);
      }
      stripes.position.set(0, 2.55, facing * 3.25);
      stripes.rotation.x = facing * 0.35;
      g.add(stripes);
      const glow = new THREE.PointLight(0xffc56b, 0, 12);
      glow.position.set(0, 3, facing * 4);
      g.add(glow);
      // roof sign (faces up-ish so it reads from the top-down camera)
      const canvas = document.createElement("canvas");
      canvas.width = 512; canvas.height = 160;
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      const sign = new THREE.Mesh(new THREE.PlaneGeometry(7.0, 2.2), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false }));
      sign.rotation.x = -Math.PI / 2 + 0.55;
      sign.position.set(0, 6.0, 0.6);
      g.add(sign);
      this.scene.add(g);
      const door3 = new THREE.Vector3(x, 0, z + facing * 4.2);
      const shop = { store: s, group: g, canvas, tex, glow, door: door3, inside: new THREE.Vector3(x, 0, z + facing * 2.2),
                     roadPoint: new THREE.Vector3(x, 0, ROAD_Z + Math.sign(z) * 1.6), revealed: false, visits: 0 };
      this.shops[s.id] = shop;
      this.drawSign(shop);
    });
  }

  drawSign(shop) {
    const c = shop.canvas.getContext("2d");
    c.clearRect(0, 0, 512, 160);
    c.fillStyle = "rgba(0,0,0,.25)";
    c.beginPath(); c.roundRect(14, 16, 492, 140, 30); c.fill();
    c.fillStyle = shop.revealed ? "#d6453a" : "#5c6680";
    c.beginPath(); c.roundRect(8, 8, 492, 140, 30); c.fill();
    c.strokeStyle = shop.revealed ? "#ffd34d" : "#8b94ab";
    c.lineWidth = 6;
    c.beginPath(); c.roundRect(16, 16, 476, 124, 24); c.stroke();
    c.fillStyle = "#fff";
    c.textAlign = "center";
    c.font = "800 60px Fraunces, Georgia, serif";
    c.fillText(shop.revealed ? shop.store.name : "Shop", 254, 88);
    c.font = "600 24px Inter, sans-serif";
    c.fillText(shop.revealed ? shop.store.kind : "not visited yet", 254, 124);
    shop.tex.needsUpdate = true;
  }

  reveal(storeId) {
    const shop = this.shops[storeId];
    if (!shop) return null;
    if (!shop.revealed) { shop.revealed = true; this.drawSign(shop); shop.pop = 1; }
    shop.glow.intensity = 40;
    shop.visits++;
    return shop;
  }

  // ---------------------------------------------------------------- elves
  setMembers(members) {
    members.forEach((m, i) => {
      if (this.elves[m.id]) return;
      const g = new THREE.Group();
      const color = COLORS[m.id] ?? 0x888888;
      const scale = m.age < 13 ? 0.78 : m.age < 18 ? 0.9 : 1;
      const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.5, 0.7, 6, 12), mat(color));
      body.position.y = 0.95;
      const belt = new THREE.Mesh(new THREE.CylinderGeometry(0.52, 0.52, 0.14, 16), mat(0x2b2b2b));
      belt.position.y = 0.85;
      const buckle = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.16, 0.06), mat(0xffd34d));
      buckle.position.set(0, 0.85, 0.52);
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.42, 18, 14), mat(0xf6d2b5));
      head.position.y = 1.95;
      const eyes = [-0.14, 0.14].map((ex) => {
        const e = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 6), mat(0x222222));
        e.position.set(ex, 2.0, 0.38);
        return e;
      });
      const hat = new THREE.Mesh(new THREE.ConeGeometry(0.44, 1.0, 14), mat(0x1f7a4d));
      hat.position.set(0, 2.6, -0.05);
      hat.rotation.x = -0.25;
      const brim = new THREE.Mesh(new THREE.TorusGeometry(0.4, 0.09, 8, 18), mat(0xffffff));
      brim.rotation.x = Math.PI / 2;
      brim.position.y = 2.2;
      const pom = new THREE.Mesh(new THREE.SphereGeometry(0.14, 10, 8), mat(0xffffff));
      pom.position.set(0, 3.05, -0.3);
      [body, head, hat].forEach((o) => (o.castShadow = true));
      g.add(body, belt, buckle, head, ...eyes, hat, brim, pom);
      const gift = new THREE.Group();
      [0xd6453a, 0x3a78c9, 0xf0c419].forEach((col, k) => {
        const b = this.giftBox(col, 0.42 - k * 0.06);
        b.position.set(0, k * 0.4, 0);
        b.rotation.y = k * 0.5;
        b.visible = false;
        gift.add(b);
      });
      gift.position.set(0.6, 1.0, 0.3);
      g.add(gift);
      g.scale.setScalar(scale * 1.15);
      g.userData.memberId = m.id;
      const a = (i / members.length) * Math.PI * 2;
      const home = new THREE.Vector3(Math.cos(a) * 4.9, 0.16, Math.sin(a) * 4.9);
      g.position.copy(home);
      const div = document.createElement("div");
      div.className = "elf-label";
      div.innerHTML = `${m.name}'s elf<span class="say"></span>`;
      const label = new CSS2DObject(div);
      label.position.set(0, 3.6, 0);
      g.add(label);
      this.scene.add(g);
      this.elves[m.id] = { member: m, group: g, home, target: null, queue: [], div, gift, phase: Math.random() * 6,
                           wanderAt: 1 + Math.random() * 3, busy: false };
    });
  }

  say(memberId, text) {
    const e = this.elves[memberId];
    if (!e) return;
    e.div.querySelector(".say").textContent = text || "";
  }

  // Walk via the road network: plaza edge -> road -> along the road -> shop's road point -> door -> inside.
  routeTo(e, shop) {
    const p = e.group.position;
    const pts = [];
    const onRoadZ = Math.abs(p.z - ROAD_Z) < 3.5, onRoadX = Math.abs(p.x - ROAD_X) < 3.5;
    if (!onRoadZ && !onRoadX) pts.push(new THREE.Vector3(p.x, 0, ROAD_Z + Math.sign(p.z || 1) * 1.6));
    pts.push(shop.roadPoint.clone().add(new THREE.Vector3((Math.random() - 0.5) * 1.5, 0, 0)));
    pts.push(shop.door.clone().add(new THREE.Vector3((Math.random() - 0.5) * 1.2, 0, 0)));
    return pts;
  }

  walkTo(memberId, storeId) {
    const e = this.elves[memberId], shop = this.shops[storeId];
    if (!e || !shop) return;
    e.busy = true;
    e.queue.push(...this.routeTo(e, shop).map((v) => ({ v })));
    e.queue.push({ v: shop.inside.clone(), enter: shop });
  }

  giveGift(memberId) {
    const e = this.elves[memberId];
    if (!e) return;
    e.gifts = (e.gifts || 0) + 1;
    e.gift.children.forEach((b, k) => (b.visible = k < e.gifts));
  }

  goHome(memberId) {
    const e = this.elves[memberId];
    if (!e) return;
    const last = e.queue.length ? e.queue[e.queue.length - 1].v : e.group.position;
    // come back out the door, along the road, then to the plaza
    const shop = Object.values(this.shops).find((s) => s.inside.distanceTo(last) < 0.5);
    if (shop) e.queue.push({ v: shop.door.clone(), exit: true }, { v: shop.roadPoint.clone() });
    e.queue.push({ v: e.home.clone(), done: true });
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    const dt = Math.min(this.clock.getDelta(), 0.05), t = this.clock.elapsedTime;
    for (const e of Object.values(this.elves)) {
      const g = e.group;
      if (!e.target && e.queue.length) e.target = e.queue.shift();
      if (e.target) {
        const d = e.target.v.clone().sub(g.position);
        d.y = 0;
        const dist = d.length();
        if (dist < 0.15) {
          if (e.target.enter) { g.visible = false; e.target.enter.glow.intensity = 40; e.hiddenUntil = t + 1.4; }
          if (e.target.exit) g.visible = true;
          if (e.target.done) { e.busy = false; e.wanderAt = t + 1 + Math.random() * 2; }
          e.target = null;
        } else {
          if (e.hiddenUntil && t < e.hiddenUntil) continue; // still inside the shop
          if (!g.visible && !e.target.enter) g.visible = true;
          const step = Math.min(dist, dt * 8);
          g.position.add(d.normalize().multiplyScalar(step));
          g.rotation.y = Math.atan2(d.x, d.z);
          g.position.y = 0.16 + Math.abs(Math.sin(t * 12 + e.phase)) * 0.28;
          g.rotation.z = Math.sin(t * 12 + e.phase) * 0.08;
        }
      } else {
        // idle: if it was inside a shop and nothing is queued, step back out
        if (!g.visible && (!e.hiddenUntil || t > e.hiddenUntil)) { g.visible = true; this.goHome(e.member.id); }
        // idle: bob, look around, and wander a little around the plaza ring
        g.position.y = 0.16 + Math.abs(Math.sin(t * 2.5 + e.phase)) * 0.06;
        g.rotation.z = 0;
        if (!e.busy && t > e.wanderAt) {
          const a = Math.random() * Math.PI * 2, r = (e.gifts ? 4.6 + Math.random() * 3.2 : 4.4 + Math.random() * 0.9);
          e.queue.push({ v: new THREE.Vector3(Math.cos(a) * r, 0.16, Math.sin(a) * r) });
          e.home = e.queue[e.queue.length - 1].v.clone();
          e.wanderAt = t + 3 + Math.random() * 4;
        }
      }
    }
    this.controls.update();
    for (const s of Object.values(this.shops)) {
      s.glow.intensity *= 0.985;
      if (s.pop) { s.pop *= 0.92; s.group.scale.setScalar(1 + s.pop * 0.08); if (s.pop < 0.01) { s.pop = 0; s.group.scale.setScalar(1); } }
    }
    for (const tw of this.twinkles) tw.m.material.emissiveIntensity = 0.4 + Math.max(0, Math.sin(t * 3 + tw.phase)) * 1.2;
    if (this.star) { this.star.rotation.y = t; }
    if (this.snow) {
      const p = this.snow.geometry.attributes.position;
      for (let i = 0; i < p.count; i++) {
        let y = p.getY(i) - dt * 2.2;
        if (y < 0) y = 30;
        p.setY(i, y);
        p.setX(i, p.getX(i) + Math.sin(t + i) * dt * 0.3);
      }
      p.needsUpdate = true;
    }
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }
}
