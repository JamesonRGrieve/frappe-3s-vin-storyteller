// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller per-code pages (card 330): reads the kind and code from the address, asks the API for the code's
// page or the kind's index, and renders it as text nodes only. Pure helpers live in storyteller-core.js.
(() => {
	"use strict";

	const core = globalThis.VinStorytellerCore;
	const MESSAGES = {
		busy: "Reading the production record…",
		failed: "The production record is unavailable right now. Please try again later.",
		limited: "You've opened a lot of code pages this hour. Please try again later.",
		invalid: "That address isn't a code page. Here is every code instead.",
	};
	const HTTP_TOO_MANY_REQUESTS = 429;
	const PAIRED = {
		paint: { kind: "interior", caption: "Interiors built in this paint", column: "Interior" },
		interior: { kind: "paint", caption: "Paints built with this interior", column: "Paint" },
	};

	function element(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined) node.textContent = text;
		return node;
	}

	// A link when there is an address, else plain text.
	function linkOrText(href, text) {
		if (!href) return document.createTextNode(text);
		const link = element("a", "", text);
		link.href = href;
		return link;
	}

	function setStatus(root, text, tone = "notice") {
		const status = root.querySelector(".vst-status");
		status.textContent = text;
		status.dataset.tone = tone;
		status.hidden = !text;
	}

	function row(cells) {
		const tr = element("tr");
		cells.forEach((cell, i) => {
			const td = element(i === 0 ? "th" : "td");
			if (i === 0) td.scope = "row";
			td.append(cell instanceof Node ? cell : document.createTextNode(cell));
			tr.append(td);
		});
		return tr;
	}

	function swatch(kind, code) {
		const span = element("span", "vst-swatch");
		span.dataset.swatchKind = kind;
		span.dataset.swatchCode = code;
		span.setAttribute("aria-hidden", "true");
		span.hidden = true; // card 329's swatch script fills it and shows it
		return span;
	}

	function modelItem(count, total) {
		const item = element("li", "vst-breakdown");
		item.append(
			element("span", "vst-n", core.formatNumber(count.count)),
			element("span", "vst-l", core.modelNoun(count)),
			element("span", "vst-breakdown-models", core.shareText(count.count, total)),
		);
		return item;
	}

	// Card 329: draw each paint or interior swatch hook with swatch.js (globalThis.VinSwatch) once it has loaded;
	// without it the hooks stay hidden.
	function fillSwatches(root) {
		const swatch = globalThis.VinSwatch;
		if (!swatch) return;
		root.querySelectorAll(".vst-swatch[data-swatch-kind]").forEach((hook) => {
			const { swatchKind: kind, swatchCode: code } = hook.dataset;
			if (!kind || !code) {
				hook.hidden = true;
				return;
			}
			swatch.render(hook, { kind, code }).then(() => {
				hook.hidden = false;
			});
		});
	}

	function renderPage(root, page) {
		const style = root.dataset.codeRoutes;
		const section = root.querySelector(".vst-code-page");
		section.querySelector(".vst-code-kind").textContent = core.KIND_NAMES[page.kind];
		const title = core.codeTitle(page);
		section.querySelector(".vst-code-title").textContent = title;
		document.title = `${title} | ${document.title}`;
		const mark = section.querySelector(".vst-code-heading .vst-swatch");
		if (page.kind === "option") {
			mark.dataset.swatchKind = "";
			mark.dataset.swatchCode = "";
		} else {
			mark.dataset.swatchKind = page.kind;
			mark.dataset.swatchCode = page.code;
		}
		section.querySelector(".vst-code-names").textContent = core.codeNamesText(page);
		section.querySelector('[data-field="total"]').textContent = core.formatNumber(page.total);
		section.querySelector('[data-field="total_label"]').textContent =
			`${page.total === 1 ? "car" : "cars"} built with this code in the factory records`;
		section.querySelector(".vst-code-span").textContent = core.spanText(page);

		section.querySelector(".vst-code-models .vst-breakdowns").replaceChildren(
			...page.by_model.map((c) => modelItem(c, page.total)),
		);
		section.querySelector(".vst-code-years tbody").replaceChildren(
			...page.by_year.map((y) => row([y.model_year, core.formatNumber(y.count), core.shareText(y.count, page.total)])),
		);
		section.querySelector(".vst-code-lines tbody").replaceChildren(
			...page.by_line.map((l) =>
				row([`${l.name} (${l.model_code})`, core.formatNumber(l.count), core.shareText(l.count, page.total)]),
			),
		);

		const pairings = section.querySelector(".vst-code-pairings");
		const paired = PAIRED[page.kind];
		if (paired) {
			pairings.querySelector("caption").textContent = paired.caption;
			pairings.querySelector(".vst-code-pairings-kind").textContent = paired.column;
			pairings.querySelector("tbody").replaceChildren(
				...page.pairings.map((p) => {
					const cell = element("span", "vst-code-cell");
					if (p.code) cell.append(swatch(paired.kind, p.code));
					cell.append(linkOrText(core.codeHref(paired.kind, p.code, "", style), core.pairingText(p)));
					return row([cell, core.formatNumber(p.count), core.shareText(p.count, page.total)]);
				}),
			);
		}
		pairings.hidden = !paired || page.pairings.length === 0;

		const fits = section.querySelector(".vst-code-fits");
		fits.querySelector(".vst-code-fits-list").replaceChildren(
			...page.fits.map((fit) => {
				const parts = core.fitParts(fit);
				const item = element("li", "vst-history-item");
				item.append(element("span", "vst-history-meta", parts.cars), element("span", "vst-history-title", parts.grade));
				const items = element("ul", "vst-equipment-list");
				items.append(...parts.items.map((text) => element("li", "", text)));
				item.append(items);
				return item;
			}),
		);
		fits.hidden = page.fits.length === 0;

		section.hidden = false;
	}

	function renderIndex(root, kind, codes) {
		const style = root.dataset.codeRoutes;
		const section = root.querySelector(".vst-code-index");
		section.querySelector(".vst-name").textContent = core.KIND_PLURALS[kind];
		section.querySelector("tbody").replaceChildren(
			...codes.map((entry) => {
				const parts = core.indexEntryParts(entry);
				const cell = element("span", "vst-code-cell");
				if (kind !== "option") cell.append(swatch(kind, entry.code));
				cell.append(linkOrText(core.codeHref(kind, entry.code, entry.model_code, style), parts.code));
				return row([cell, parts.description, parts.total, parts.models]);
			}),
		);
		section.hidden = false;
	}

	async function fetchJson(url) {
		const response = await fetch(url, { headers: { Accept: "application/json" } });
		if (response.status === HTTP_TOO_MANY_REQUESTS) return { status: "limited" };
		if (!response.ok) return { status: "error" };
		return (await response.json()).message;
	}

	async function show(root, route) {
		setStatus(root, MESSAGES.busy, "busy");
		root.querySelectorAll(".vst-code-nav a").forEach((link) => {
			if (link.dataset.kind === route.kind) link.setAttribute("aria-current", "page");
		});
		try {
			if (route.code) {
				const query = new URLSearchParams({ kind: route.kind, code: route.code, model: route.model });
				const reply = await fetchJson(`${root.dataset.codeEndpoint}?${query}`);
				if (reply.status === "found") {
					setStatus(root, "");
					renderPage(root, reply.page);
					fillSwatches(root);
					return;
				}
				if (reply.status !== "not_found") {
					setStatus(root, reply.status === "limited" ? MESSAGES.limited : MESSAGES.failed, "error");
					return;
				}
				setStatus(root, reply.message, "notice");
			}
			const reply = await fetchJson(`${root.dataset.indexEndpoint}?${new URLSearchParams({ kind: route.kind })}`);
			if (reply.status !== "found") {
				setStatus(root, reply.status === "limited" ? MESSAGES.limited : MESSAGES.failed, "error");
				return;
			}
			if (!route.code) setStatus(root, route.invalid ? MESSAGES.invalid : "", "notice");
			renderIndex(root, route.kind, reply.codes);
			fillSwatches(root);
		} catch {
			setStatus(root, MESSAGES.failed, "error");
		}
	}

	document.querySelectorAll(".vst-codes").forEach((root) => {
		const route = core.parseCodeRoute(location.pathname, location.search);
		if (route) show(root, route);
		else setStatus(root, MESSAGES.invalid, "notice");
	});
})();
