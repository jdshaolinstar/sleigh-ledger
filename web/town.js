// Top-down 3D town: six shops around a plaza, one elf per family member.
// Shop signs start blank ("Shop") and flip to the store's name when an elf heads there.
import * as THREE from "three";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const COLORS = { mom: 0xc8372d, dad: 0x2f6db5, jill: 0x8e44ad, sam: 0x1f7a4d, bill: 0xe67e22, lucy: 0xe84393 };
const SHOP_COLORS = [0xf2d6a2, 0xcfe3f5, 0xf5cfd4, 0xd5ecd4, 0xe8dcf5, 0xf5e6c8];

export class Town {
  constructor(el) {
    this.el = el;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x0f1a2b);
    const { clientWidth: w, clientHeight: h } = el;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setSize(w, h);
    this.renderer.shadowMap.enabled = true;
    el.appendChild(this.renderer.domElement);
    this.labels = new CSS2DRenderer();
    this.labels.setSize(w, h);
    Object.assign(this.labels.domElement.style, { position: "absolute", top: "0", left: "0", pointerEvents: "none" });
    el.appendChild(this.labels.domElement);

    // Steep, slightly tilted top-down camera (orthographic so the whole town fits).
    this.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200);
    this.camera.position.set(0, 40, 22);
    this.camera.lookAt(0, 0, 1);
    this.resize();
    addEventListener("resize", () => this.resize());

    this.scene.add(new THREE.HemisphereLight(0xdfeaff, 0x334466, 1.4));
    const sun = new THREE.DirectionalLight(0xfff1d6, 1.6);
    sun.position.set(12, 30, 10);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -30, right: 30, top: 30, bottom: -30 });
    this.scene.add(sun);

    this.shops = {};
    this.elves = {};
    this.clock = new THREE.Clock();
    this.buildGround();
    this.animate();
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight, aspect = w / h;
    const view = 19;
    Object.assign(this.camera, { left: -view * aspect, right: view * aspect, top: view, bottom: -view });
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.labels.setSize(w, h);
  }

  buildGround() {
    const snow = new THREE.Mesh(new THREE.PlaneGeometry(90, 70), new THREE.MeshStandardMaterial({ color: 0xeef3f8 }));
    snow.rotation.x = -Math.PI / 2;
    snow.receiveShadow = true;
    this.scene.add(snow);
    const road = new THREE.MeshStandardMaterial({ color: 0x9aa4b2 });
    for (const [w, d] of [[70, 4], [4, 50]]) {
      const r = new THREE.Mesh(new THREE.PlaneGeometry(w, d), road);
      r.rotation.x = -Math.PI / 2;
      r.position.y = 0.01;
      r.receiveShadow = true;
      this.scene.add(r);
    }
    const plaza = new THREE.Mesh(new THREE.CircleGeometry(5.5, 40), new THREE.MeshStandardMaterial({ color: 0xd8cbb3 }));
    plaza.rotation.x = -Math.PI / 2;
    plaza.position.y = 0.02;
    this.scene.add(plaza);
    // Christmas tree in the plaza
    const tree = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 1), new THREE.MeshStandardMaterial({ color: 0x7a4b2a }));
    trunk.position.y = 0.5;
    tree.add(trunk);
    [[2.2, 2.4, 1.6], [1.7, 2, 2.8], [1.1, 1.6, 3.8]].forEach(([r, hgt, y]) => {
      const c = new THREE.Mesh(new THREE.ConeGeometry(r, hgt, 10), new THREE.MeshStandardMaterial({ color: 0x1f7a4d }));
      c.position.y = y;
      c.castShadow = true;
      tree.add(c);
    });
    const star = new THREE.Mesh(new THREE.OctahedronGeometry(0.4), new THREE.MeshStandardMaterial({ color: 0xffd34d, emissive: 0xaa8800 }));
    star.position.y = 4.9;
    tree.add(star);
    this.scene.add(tree);
    // a few snowy pines around the edges
    for (let i = 0; i < 22; i++) {
      const p = new THREE.Mesh(new THREE.ConeGeometry(0.8, 2, 7), new THREE.MeshStandardMaterial({ color: 0x2c6e4f }));
      const a = (i / 22) * Math.PI * 2;
      p.position.set(Math.cos(a) * 30 + Math.sin(i * 7) * 2, 1, Math.sin(a) * 21 + Math.cos(i * 3));
      p.castShadow = true;
      this.scene.add(p);
    }
  }

  setStores(stores) {
    const spots = [[-17, -10], [0, -12.5], [17, -10], [-17, 10], [0, 12.5], [17, 10]];
    stores.forEach((s, i) => {
      if (this.shops[s.id]) return;
      const [x, z] = spots[i % spots.length];
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      const body = new THREE.Mesh(new THREE.BoxGeometry(8, 3.2, 5.5), new THREE.MeshStandardMaterial({ color: SHOP_COLORS[i % 6] }));
      body.position.y = 1.6;
      body.castShadow = body.receiveShadow = true;
      g.add(body);
      const roof = new THREE.Mesh(new THREE.BoxGeometry(8.6, 0.5, 6.1), new THREE.MeshStandardMaterial({ color: 0xffffff }));
      roof.position.y = 3.45;
      roof.castShadow = true;
      g.add(roof);
      const door = new THREE.Mesh(new THREE.BoxGeometry(1.4, 2, 0.1), new THREE.MeshStandardMaterial({ color: 0x5b3a22 }));
      const facing = z < 0 ? 1 : -1; // doors face the main road
      door.position.set(0, 1, facing * 2.8);
      g.add(door);
      const glow = new THREE.PointLight(0xffc56b, 0, 10);
      glow.position.set(0, 4.5, 0);
      g.add(glow);
      // roof sign (faces up so it reads from the top-down camera)
      const canvas = document.createElement("canvas");
      canvas.width = 512; canvas.height = 160;
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      const sign = new THREE.Mesh(new THREE.PlaneGeometry(7.6, 2.4), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
      sign.rotation.x = -Math.PI / 2 + 0.35;
      sign.position.set(0, 4.6, 0.2);
      g.add(sign);
      this.scene.add(g);
      const shop = { store: s, group: g, canvas, tex, glow, door: new THREE.Vector3(x, 0, z + facing * 4), revealed: false, visits: 0 };
      this.shops[s.id] = shop;
      this.drawSign(shop);
    });
  }

  drawSign(shop) {
    const c = shop.canvas.getContext("2d");
    c.clearRect(0, 0, 512, 160);
    c.fillStyle = shop.revealed ? "#c8372d" : "#56607a";
    c.beginPath(); c.roundRect(8, 8, 496, 144, 28); c.fill();
    c.fillStyle = "#fff";
    c.textAlign = "center";
    c.font = "800 62px Fraunces, Georgia, serif";
    c.fillText(shop.revealed ? shop.store.name : "Shop", 256, 92);
    c.font = "500 26px Inter, sans-serif";
    c.fillText(shop.revealed ? shop.store.kind : "not visited yet", 256, 132);
    shop.tex.needsUpdate = true;
  }

  reveal(storeId) {
    const shop = this.shops[storeId];
    if (!shop) return null;
    if (!shop.revealed) { shop.revealed = true; this.drawSign(shop); }
    shop.glow.intensity = 30;
    shop.visits++;
    return shop;
  }

  setMembers(members) {
    members.forEach((m, i) => {
      if (this.elves[m.id]) return;
      const g = new THREE.Group();
      const color = COLORS[m.id] ?? 0x888888;
      const scale = m.age < 13 ? 0.75 : m.age < 18 ? 0.88 : 1;
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.6, 1.3, 12), new THREE.MeshStandardMaterial({ color }));
      body.position.y = 0.65;
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.42, 16, 12), new THREE.MeshStandardMaterial({ color: 0xf3d2b3 }));
      head.position.y = 1.6;
      const hat = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.9, 12), new THREE.MeshStandardMaterial({ color: 0x1f7a4d }));
      hat.position.y = 2.25;
      const pom = new THREE.Mesh(new THREE.SphereGeometry(0.13), new THREE.MeshStandardMaterial({ color: 0xffffff }));
      pom.position.y = 2.72;
      [body, head, hat].forEach((o) => (o.castShadow = true));
      g.add(body, head, hat, pom);
      g.scale.setScalar(scale * 1.25);
      const a = (i / members.length) * Math.PI * 2;
      const home = new THREE.Vector3(Math.cos(a) * 7, 0, Math.sin(a) * 7);
      g.position.copy(home);
      const div = document.createElement("div");
      div.className = "elf-label";
      div.innerHTML = `${m.name}'s elf<span class="say"></span>`;
      const label = new CSS2DObject(div);
      label.position.set(0, 3.2, 0);
      g.add(label);
      this.scene.add(g);
      this.elves[m.id] = { member: m, group: g, home, target: null, queue: [], div, phase: Math.random() * 6 };
    });
  }

  say(memberId, text) {
    const e = this.elves[memberId];
    if (!e) return;
    e.div.querySelector(".say").textContent = text || "";
  }

  walkTo(memberId, storeId) {
    const e = this.elves[memberId], shop = this.shops[storeId];
    if (!e || !shop) return;
    e.queue.push(shop.door.clone().add(new THREE.Vector3((Math.random() - 0.5) * 3, 0, 0)));
  }

  goHome(memberId) {
    const e = this.elves[memberId];
    if (e) e.queue.push(e.home.clone());
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    const dt = Math.min(this.clock.getDelta(), 0.05), t = this.clock.elapsedTime;
    for (const e of Object.values(this.elves)) {
      if (!e.target && e.queue.length) e.target = e.queue.shift();
      if (e.target) {
        const d = e.target.clone().sub(e.group.position);
        d.y = 0;
        const dist = d.length();
        if (dist < 0.15) { e.target = null; }
        else {
          const step = Math.min(dist, dt * 9);
          e.group.position.add(d.normalize().multiplyScalar(step));
          e.group.rotation.y = Math.atan2(d.x, d.z);
          e.group.position.y = Math.abs(Math.sin(t * 12 + e.phase)) * 0.25;
        }
      } else {
        e.group.position.y = Math.abs(Math.sin(t * 2 + e.phase)) * 0.05;
      }
    }
    for (const s of Object.values(this.shops)) s.glow.intensity *= 0.985;
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }
}
