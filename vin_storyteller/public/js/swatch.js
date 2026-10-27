// SPDX-License-Identifier: AGPL-3.0-or-later
// Animated paint and interior swatches. Paint is drawn from a bump map (orange peel) and a spectral flake
// map (metallic / pearl flake, interference colour, clearcoat highlight); interiors are perforated leather
// or a cloth weave. The light follows the cursor on desktop and the scroll on touch screens, and holds
// still under prefers-reduced-motion. One shared WebGL context draws every swatch on the page; without
// WebGL a swatch falls back to a still CSS gradient in its colour.
//
// Pure logic lives in swatch-core.js (globalThis.VinSwatchCore), which must load first. The code tables
// ship as /assets/vin_storyteller/data/swatches.json.
//
// Use (exposed as globalThis.VinSwatch):
//   Declarative: <div data-swatch="paint" data-code="W75" data-description="" data-caption></div>
//                (data-swatch="interior" for trim). Elements present at DOMContentLoaded are mounted; call
//                VinSwatch.mountAll(root) for markup added later.
//   Scripted:    VinSwatch.render(element, { kind: "paint" | "interior", code, description, caption })
//                -> Promise of the swatch model (status, name, finish / material, label).
//   VinSwatch.configure({ src }) points at another copy of swatches.json (before the first render).
//   VinSwatch.unmount(element) stops drawing it.
(() => {
	"use strict";

	const core = globalThis.VinSwatchCore;
	if (!core || globalThis.VinSwatch) return;

	const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
	const FINE_POINTER = "(hover: hover) and (pointer: fine)";
	const EMPTY_DATA = Object.freeze({ paint: {}, interior: {} });
	let dataSource = "/assets/vin_storyteller/data/swatches.json";
	let dataPromise = null;

	function loadData() {
		if (!dataPromise) {
			dataPromise = fetch(dataSource, { credentials: "omit", headers: { Accept: "application/json" } })
				.then((response) => (response.ok ? response.json() : EMPTY_DATA))
				.then((data) => ({ paint: data.paint || {}, interior: data.interior || {} }))
				.catch(() => EMPTY_DATA);
		}
		return dataPromise;
	}

	// ---- WebGL: one offscreen context, copied into each swatch's 2D canvas ----

	const VERTEX = `
attribute vec2 aPos;
varying vec2 vUv;
void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`;

	const FRAGMENT = `
precision highp float;
varying vec2 vUv;
uniform vec2 uRes;      // device pixels drawn
uniform float uUnit;    // device pixels per CSS pixel, so textures keep their size
uniform vec2 uLight;    // -1..1, x right, y down
uniform int uMode;      // 0 paint, 1 leather, 2 cloth, 3 plain
uniform vec3 uBase;     // linear
uniform vec3 uFlake;    // linear
uniform vec4 uFinish;   // flake density, flake size, flake strength, pearl
uniform vec2 uSurface;  // gloss, bump (peel / grain) height
uniform float uSeed;

float hash(vec2 p) {
	p = fract(p * vec2(123.34, 456.21) + uSeed * 0.0137);
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}
vec2 hash2(vec2 p) { float h = hash(p); return vec2(h, hash(p + h + 17.0)); }
float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
	float a = 0.5;
	float s = 0.0;
	for (int i = 0; i < 4; i++) { s += a * noise(p); p *= 2.03; a *= 0.5; }
	return s;
}
// Cellular grain for leather: distance to the nearest jittered point.
float cells(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	float d = 1.0;
	for (int y = -1; y <= 1; y++) {
		for (int x = -1; x <= 1; x++) {
			vec2 o = vec2(float(x), float(y));
			d = min(d, length(o + hash2(i + o) - f));
		}
	}
	return d;
}

// Perforation: staggered holes; returns 0 at a hole's centre, 1 on the hide.
const float PITCH = 9.0;
float perforation(vec2 p) {
	vec2 q = p / PITCH;
	q.x += 0.5 * mod(floor(q.y), 2.0);
	vec2 c = fract(q) - 0.5;
	return smoothstep(0.14, 0.22, length(c));
}
// Plain weave: warp and weft alternate over and under; returns thread height and which thread is on top.
const float THREAD = 4.0;
vec2 weave(vec2 p) {
	vec2 q = p / THREAD;
	vec2 cell = floor(q);
	vec2 f = fract(q);
	float warpOnTop = mod(cell.x + cell.y, 2.0);
	float warp = sin(3.14159 * f.x) * (0.6 + 0.4 * sin(3.14159 * f.y));
	float weft = sin(3.14159 * f.y) * (0.6 + 0.4 * sin(3.14159 * f.x));
	float h = mix(weft, warp, warpOnTop);
	return vec2(h + 0.15 * noise(p * 1.7), warpOnTop);
}

float heightAt(vec2 p) {
	if (uMode == 1) {
		float grain = 1.0 - cells(p * 0.32);
		float crease = abs(noise(p * 0.05) - 0.5);
		return uSurface.y * (0.55 * grain - 0.6 * crease) - 1.6 * (1.0 - perforation(p));
	}
	if (uMode == 2) return uSurface.y * weave(p).x;
	if (uMode == 3) return 0.15 * noise(p * vec2(0.05, 0.6));
	return uSurface.y * 0.25 * fbm(p * 0.09); // orange peel under the clearcoat
}

void main() {
	vec2 p = gl_FragCoord.xy / uUnit;
	float aspect = uRes.x / max(uRes.y, 1.0);
	vec2 uv = vec2(vUv.x * aspect, vUv.y);

	// A gently curved panel, so the highlight travels across it as the light moves.
	vec3 n0 = normalize(vec3((vUv.x - 0.5) * 0.45, (vUv.y - 0.5) * 0.3, 1.0));
	float h = heightAt(p);
	vec2 grad = vec2(heightAt(p + vec2(1.0, 0.0)) - h, heightAt(p + vec2(0.0, 1.0)) - h);
	vec3 n = normalize(n0 + vec3(-grad, 0.0));

	vec3 lightPos = vec3(aspect * (0.5 + uLight.x * 0.75), 0.5 - uLight.y * 0.75, 0.7);
	vec3 l = normalize(lightPos - vec3(uv, 0.0));
	vec3 v = vec3(0.0, 0.0, 1.0);
	vec3 hv = normalize(l + v);
	float diffuse = max(dot(n, l), 0.0);
	float ndoth = max(dot(n, hv), 0.0);
	float ndotv = max(dot(n, v), 0.0);
	vec3 colour;

	if (uMode == 0) {
		float density = uFinish.x;
		float size = uFinish.y;
		float strength = uFinish.z;
		float pearl = uFinish.w;
		// Flop: metallic and pearl paint is brighter facing the highlight and darker away from it.
		float flop = mix(1.0, mix(0.45, 1.3, pow(ndoth, 3.0)), clamp(density + pearl, 0.0, 1.0));
		vec3 body = uBase * (0.18 + 0.82 * diffuse) * flop;
		// Spectral map: the interference colour shifts with the angle to the light.
		float t = dot(n, hv) * 1.6 + vUv.x * 0.35 + uLight.x * 0.25;
		vec3 spectrum = 0.5 + 0.5 * cos(6.28318 * (vec3(0.0, 0.33, 0.67) + t));
		vec3 pearlTint = mix(uFlake, uFlake * (0.55 + 0.9 * spectrum), 0.45);
		body = mix(body, pearlTint * (0.25 + 1.1 * pow(ndoth, 6.0)), pearl * 0.55);
		// Flake map: each cell may hold a flake with its own tilt; a flake sparkles when it faces the half-vector.
		vec3 sparkle = vec3(0.0);
		for (int layer = 0; layer < 2; layer++) {
			float scale = size * (layer == 0 ? 1.0 : 2.3);
			vec2 cell = floor(p / scale) + float(layer) * 31.0;
			vec2 r = hash2(cell);
			float present = step(1.0 - density * (layer == 0 ? 1.0 : 0.5), r.x);
			vec3 fn = normalize(n0 + vec3((hash2(cell + 7.3) - 0.5) * 0.9, 0.0));
			float glint = pow(max(dot(fn, hv), 0.0), 90.0 + 160.0 * r.y);
			vec3 tint = mix(uFlake, uFlake * (0.4 + 1.2 * spectrum), pearl);
			sparkle += tint * glint * present * strength * (layer == 0 ? 1.6 : 2.2);
		}
		// Clearcoat: a sharp highlight over the peel, a broad sheen, and a dim sky reflection.
		float gloss = uSurface.x;
		float fresnel = 0.04 + 0.96 * pow(1.0 - ndotv, 5.0);
		float coat = pow(ndoth, mix(60.0, 900.0, gloss)) * (2.4 + 3.0 * gloss);
		float sheen = pow(ndoth, 14.0) * 0.12;
		vec3 sky = mix(vec3(0.02, 0.025, 0.03), vec3(0.22, 0.25, 0.3), vUv.y) * (0.25 + fresnel);
		colour = body + sparkle + vec3(coat + sheen) + sky * 0.35;
	} else if (uMode == 1) {
		float hole = perforation(p);
		float tone = 0.88 + 0.18 * fbm(p * 0.04);
		vec3 hide = uBase * tone * (0.22 + 0.85 * diffuse);
		float sheen = pow(ndoth, 20.0) * (0.12 + 0.5 * uSurface.x);
		colour = mix(uBase * 0.05, hide + vec3(sheen) * mix(vec3(1.0), uBase + 0.4, 0.4), hole);
	} else if (uMode == 2) {
		vec2 w = weave(p);
		vec2 thread = floor(p / THREAD);
		float heather = 0.8 + 0.35 * hash(thread + w.y * 13.0) + 0.1 * noise(p * 0.3);
		vec3 yarn = uBase * heather * (0.3 + 0.75 * diffuse) * (0.75 + 0.35 * w.x);
		float velvet = pow(1.0 - ndotv, 2.0) * 0.5 + pow(ndoth, 6.0) * 0.08;
		colour = yarn + uBase * velvet;
	} else {
		colour = uBase * (0.35 + 0.65 * diffuse) + vec3(pow(ndoth, 30.0) * 0.08);
	}

	colour = colour / (1.0 + 0.18 * colour);         // soft shoulder for highlights
	colour = pow(clamp(colour, 0.0, 1.0), vec3(1.0 / 2.2)); // linear to display
	gl_FragColor = vec4(colour, 1.0);
}`;

	let renderer; // undefined: not tried yet; null: no WebGL here

	function compile(gl, type, source) {
		const shader = gl.createShader(type);
		gl.shaderSource(shader, source);
		gl.compileShader(shader);
		return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
	}

	function createRenderer() {
		const canvas = document.createElement("canvas");
		const gl =
			canvas.getContext("webgl", { preserveDrawingBuffer: true, antialias: false, premultipliedAlpha: false }) ||
			canvas.getContext("experimental-webgl", { preserveDrawingBuffer: true });
		if (!gl) return null;
		const vs = compile(gl, gl.VERTEX_SHADER, VERTEX);
		const fs = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
		if (!vs || !fs) return null;
		const program = gl.createProgram();
		gl.attachShader(program, vs);
		gl.attachShader(program, fs);
		gl.linkProgram(program);
		if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
		gl.useProgram(program);
		const buffer = gl.createBuffer();
		gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
		gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
		const position = gl.getAttribLocation(program, "aPos");
		gl.enableVertexAttribArray(position);
		gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
		const at = (name) => gl.getUniformLocation(program, name);
		const uniforms = {};
		for (const name of ["uRes", "uUnit", "uLight", "uMode", "uBase", "uFlake", "uFinish", "uSurface", "uSeed"]) {
			uniforms[name] = at(name);
		}
		const state = { canvas, gl, uniforms, lost: false };
		canvas.addEventListener("webglcontextlost", (event) => {
			event.preventDefault();
			state.lost = true;
			for (const record of records.values()) fallBack(record);
		});
		return state;
	}

	function getRenderer() {
		if (renderer === undefined) {
			try {
				renderer = createRenderer();
			} catch {
				renderer = null;
			}
		}
		return renderer && !renderer.lost ? renderer : null;
	}

	function draw(record) {
		const r = getRenderer();
		if (!r) return fallBack(record);
		const { gl, uniforms: u, canvas } = r;
		const size = core.canvasSize(record.element.clientWidth, record.element.clientHeight, globalThis.devicePixelRatio);
		if (record.canvas.width !== size.width || record.canvas.height !== size.height) {
			record.canvas.width = size.width;
			record.canvas.height = size.height;
		}
		if (canvas.width < size.width || canvas.height < size.height) {
			canvas.width = Math.max(canvas.width, size.width);
			canvas.height = Math.max(canvas.height, size.height);
		}
		gl.viewport(0, 0, size.width, size.height);
		const v = record.uniforms;
		gl.uniform2f(u.uRes, size.width, size.height);
		gl.uniform1f(u.uUnit, size.width / Math.max(1, record.element.clientWidth));
		gl.uniform2f(u.uLight, record.light.x, record.light.y);
		gl.uniform1i(u.uMode, v.mode);
		gl.uniform3fv(u.uBase, v.base);
		gl.uniform3fv(u.uFlake, v.flake);
		gl.uniform4fv(u.uFinish, v.finish);
		gl.uniform2fv(u.uSurface, v.surface);
		gl.uniform1f(u.uSeed, v.seed);
		gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
		// WebGL draws from the bottom-left; the 2D copy reads from the top-left.
		record.context.drawImage(canvas, 0, canvas.height - size.height, size.width, size.height, 0, 0, size.width, size.height);
	}

	function fallBack(record) {
		record.element.classList.add("vsw--static");
		record.element.style.backgroundImage = core.staticBackground(record.swatch);
	}

	// ---- Motion ----

	const records = new Map(); // element -> record
	let mode = "still";
	let pointerTarget = { ...core.REST_LIGHT };
	let frame = 0;
	let lastTime = 0;

	const media = (query) => (globalThis.matchMedia ? globalThis.matchMedia(query) : { matches: false });
	function readMode() {
		mode = core.motionMode({ reducedMotion: media(REDUCED_MOTION).matches, finePointer: media(FINE_POINTER).matches });
	}

	function targetFor(record) {
		if (mode === "pointer") return pointerTarget;
		if (mode === "scroll") {
			const box = record.element.getBoundingClientRect();
			return core.lightFromScroll(box.top + box.height / 2, globalThis.innerHeight);
		}
		return core.REST_LIGHT;
	}

	function tick(time) {
		frame = 0;
		const dt = lastTime ? Math.min(0.1, (time - lastTime) / 1000) : 0.016;
		lastTime = time;
		let moving = false;
		for (const record of records.values()) {
			if (!record.visible) continue;
			const target = targetFor(record);
			const next = mode === "still" ? target : core.approach(record.light, target, dt);
			if (record.dirty || !core.settled(record.light, next, 1e-4)) {
				record.light = next;
				record.dirty = false;
				draw(record);
			}
			if (!core.settled(record.light, target)) moving = true;
		}
		if (moving) schedule();
		else lastTime = 0;
	}
	function schedule() {
		if (!frame) frame = requestAnimationFrame(tick);
	}

	let listening = false;
	function listen() {
		if (listening) return;
		listening = true;
		readMode();
		globalThis.addEventListener(
			"pointermove",
			(event) => {
				if (mode !== "pointer") return;
				pointerTarget = core.lightFromPointer(event.clientX, event.clientY, globalThis.innerWidth, globalThis.innerHeight);
				schedule();
			},
			{ passive: true },
		);
		globalThis.addEventListener("scroll", () => mode === "scroll" && schedule(), { passive: true });
		globalThis.addEventListener("resize", () => {
			for (const record of records.values()) record.dirty = true;
			schedule();
		});
		for (const query of [REDUCED_MOTION, FINE_POINTER]) {
			const list = media(query);
			if (list.addEventListener) {
				list.addEventListener("change", () => {
					readMode();
					for (const record of records.values()) record.dirty = true;
					schedule();
				});
			}
		}
	}

	const observer =
		"IntersectionObserver" in globalThis
			? new IntersectionObserver((entries) => {
					for (const entry of entries) {
						const record = records.get(entry.target);
						if (!record) continue;
						record.visible = entry.isIntersecting;
						if (record.visible) record.dirty = true;
					}
					schedule();
				})
			: null;

	// ---- Mounting ----

	function element(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined) node.textContent = text;
		return node;
	}

	function swatchFor(data, kind, code, description) {
		const key = String(code ?? "").trim().toUpperCase();
		if (kind === "interior") return core.interiorSwatch(data.interior[key], description);
		return core.paintSwatch(data.paint[key], description);
	}

	function unmount(target) {
		const record = records.get(target);
		if (!record) return;
		observer?.unobserve(target);
		records.delete(target);
	}

	// Draw a swatch into `target` (its size comes from CSS: .vsw sets an aspect ratio). Replaces whatever the
	// element held. Resolves to the swatch model so callers can write their own caption.
	async function render(target, { kind = "paint", code = "", description = "", caption = false } = {}) {
		const data = await loadData();
		const swatch = swatchFor(data, kind, code, description);
		unmount(target);
		const parts = core.captionParts(swatch, String(code ?? "").trim().toUpperCase());
		const canvas = element("canvas", "vsw-canvas");
		canvas.setAttribute("aria-hidden", "true");
		const children = [canvas];
		if (swatch.label === core.NOT_ON_FILE) children.push(element("span", "vsw-badge", core.NOT_ON_FILE));
		if (caption) {
			const text = element("span", "vsw-caption");
			text.append(element("span", "vsw-title", parts.title), element("span", "vsw-detail", parts.detail));
			children.push(text);
		}
		target.classList.add("vsw", `vsw--${kind === "interior" ? "interior" : "paint"}`);
		target.classList.remove("vsw--static");
		target.style.backgroundImage = "";
		target.dataset.status = swatch.status;
		target.dataset.finish = swatch.finish || swatch.material || "";
		target.setAttribute("role", "img");
		target.setAttribute("aria-label", [parts.title, parts.detail].filter(Boolean).join(", "));
		target.replaceChildren(...children);

		const record = {
			element: target,
			canvas,
			context: canvas.getContext("2d"),
			swatch,
			uniforms: core.uniformsFor(swatch, core.seedFor(`${kind}:${code}`)),
			light: { ...core.REST_LIGHT },
			visible: !observer,
			dirty: true,
		};
		records.set(target, record);
		listen();
		if (!record.context) fallBack(record);
		if (observer) observer.observe(target);
		schedule();
		return swatch;
	}

	function mountAll(root = document) {
		const nodes = root.querySelectorAll("[data-swatch]");
		return Promise.all(
			Array.from(nodes, (node) =>
				render(node, {
					kind: node.dataset.swatch,
					code: node.dataset.code || "",
					description: node.dataset.description || "",
					caption: node.hasAttribute("data-caption"),
				}),
			),
		);
	}

	function configure({ src } = {}) {
		if (src) {
			dataSource = src;
			dataPromise = null;
		}
	}

	globalThis.VinSwatch = Object.freeze({ render, mountAll, unmount, configure, load: loadData });

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => mountAll());
	else mountAll();
})();
