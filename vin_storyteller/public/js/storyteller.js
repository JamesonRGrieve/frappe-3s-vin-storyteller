// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller front end: asks the storyteller API for a VIN's story and renders it as text nodes only.
// Pure helpers live in storyteller-core.js (globalThis.VinStorytellerCore), loaded first.
(() => {
	"use strict";

	const core = globalThis.VinStorytellerCore;
	const MESSAGES = {
		invalid: "Please enter a valid 17 character VIN. VINs never contain the letters I, O or Q.",
		name: "Please enter your name. Every story told is logged with the name given.",
		busy: "Reading the production record…",
		failed: "The storyteller is unavailable right now. Please try again later.",
		limited: (limit) => `You've used your ${limit} lookups for this hour. Please try again in an hour.`,
	};
	const BUTTON_LABEL = "Tell its story";
	const BUSY_LABEL = "Reading the record…";
	const DEFAULT_LIMIT = 3;
	const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
	const HTTP_TOO_MANY_REQUESTS = 429;

	function element(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined) node.textContent = text;
		return node;
	}

	// The status line: hidden when empty; `tone` (busy | error | notice) picks its colour.
	function setStatus(root, text, tone = "notice") {
		const status = root.querySelector(".vst-status");
		status.textContent = text;
		status.dataset.tone = tone;
		status.hidden = !text;
	}

	function setBusy(root, busy) {
		const button = root.querySelector(".vst-submit");
		button.disabled = busy;
		button.setAttribute("aria-busy", String(busy));
		button.querySelector(".vst-submit-label").textContent = busy ? BUSY_LABEL : BUTTON_LABEL;
	}

	// Live feedback while typing: the character count and, once something is wrong, why.
	function showCheck(root, input) {
		const check = core.vinCheck(input.value);
		const count = root.querySelector(".vst-count");
		count.textContent = check.count;
		count.dataset.state = check.state;
		root.querySelector(".vst-check").textContent = check.message;
		if (check.state === "bad") input.setAttribute("aria-invalid", "true");
		else input.removeAttribute("aria-invalid");
	}

	function setText(root, field, text) {
		root.querySelector(`[data-field="${field}"]`).textContent = text;
	}

	function specRow(label, value) {
		const row = element("tr");
		const th = element("th", "", label);
		th.scope = "row";
		row.append(th, element("td", "", value));
		return row;
	}

	function badge(rarity) {
		const parts = core.badgeParts(rarity);
		const item = element("li", `vst-badge vst-tier-${rarity.tier}`);
		item.append(
			element("span", "vst-badge-tier", parts.tier),
			element("span", "vst-badge-count", parts.count),
			element("span", "vst-badge-scope", parts.scope),
		);
		return item;
	}

	function historyItem(record) {
		const parts = core.historyParts(record);
		const item = element("li", "vst-history-item");
		item.append(element("span", "vst-history-meta", parts.meta));
		if (parts.url) {
			const link = element("a", "vst-history-title", parts.title);
			link.href = parts.url;
			link.rel = "noopener noreferrer nofollow";
			link.target = "_blank";
			item.append(link);
		} else {
			item.append(element("span", "vst-history-title", parts.title));
		}
		item.append(element("span", "vst-history-source", parts.source));
		return item;
	}

	function render(root, story) {
		const result = root.querySelector(".vst-result");
		result.querySelector(".vst-name").textContent = story.vehicle_name;
		result.querySelector(".vst-built").textContent = core.builtText(story);
		result.querySelector(".vst-stats").hidden = Boolean(story.partial);
		result.querySelector(".vst-timeline").hidden = Boolean(story.partial);
		result.querySelector(".vst-vin-value").textContent = story.vin;

		setText(result, "in_year", core.positionText(story.in_year));
		setText(result, "in_year_label", `built for the ${story.model_year} model year (any model or trim)`);
		setText(result, "in_model", core.positionText(story.in_model));
		setText(result, "in_model_label", `${story.vehicle_name}s built`);
		setText(result, "in_colour", core.positionText(story.in_colour));
		setText(result, "in_colour_label", `${story.vehicle_name}s in ${story.exterior.description}`);
		setText(result, "among_identical", core.positionText(story.among_identical));
		setText(result, "built_in_period", core.formatNumber(story.built_in_period));
		setText(result, "built_in_month", core.formatNumber(story.built_in_month));

		if (story.rarest) result.dataset.rarity = story.rarest;
		else delete result.dataset.rarity;
		const badges = result.querySelector(".vst-badges");
		badges.replaceChildren(...story.rarities.map(badge));
		badges.hidden = story.rarities.length === 0;

		result.querySelector(".vst-timeline").textContent = core.timelineText(story);
		result.querySelector(".vst-spec tbody").replaceChildren(
			specRow("Model year", story.model_year || "Not known"),
			specRow("Manufacturer", story.manufacturer),
			specRow("Model", story.model),
			specRow("Trim", story.trim || "—"),
			specRow("Exterior colour", core.codedText(story.exterior)),
			specRow("Interior colour", core.codedText(story.interior)),
			specRow("Equipment", core.codedText(story.equipment)),
			specRow(story.vin.length === 17 ? "VIN" : "Chassis number", story.vin),
		);
		result.querySelector(".vst-provenance").textContent = core.provenanceText(story.provenance);

		const history = result.querySelector(".vst-history");
		history.querySelector(".vst-history-list").replaceChildren(...story.history.map(historyItem));
		history.hidden = story.history.length === 0;

		result.hidden = false;
		result.focus({ preventScroll: true });
		result.scrollIntoView({ behavior: matchMedia(REDUCED_MOTION).matches ? "auto" : "smooth", block: "start" });
	}

	async function tell(root, vin, name) {
		root.querySelector(".vst-result").hidden = true;
		setStatus(root, MESSAGES.busy, "busy");
		setBusy(root, true);
		try {
			const url = `${root.dataset.endpoint}?vin=${encodeURIComponent(vin)}&name=${encodeURIComponent(name)}`;
			const response = await fetch(url, { headers: { Accept: "application/json" } });
			if (response.status === HTTP_TOO_MANY_REQUESTS) {
				setStatus(root, MESSAGES.limited(Number(root.dataset.limit) || DEFAULT_LIMIT), "error");
				return;
			}
			if (!response.ok) {
				setStatus(root, MESSAGES.failed, "error");
				return;
			}
			const { message: reply } = await response.json();
			if (reply.status === "found") {
				setStatus(root, "");
				render(root, reply.story);
			} else {
				setStatus(root, reply.message || MESSAGES.failed, reply.status === "not_found" ? "notice" : "error");
			}
		} catch {
			setStatus(root, MESSAGES.failed, "error");
		} finally {
			setBusy(root, false);
		}
	}

	function mount(root) {
		const form = root.querySelector(".vst-form");
		const input = form.querySelector("input[name=vin]");
		input.addEventListener("input", () => showCheck(root, input));
		form.addEventListener("submit", (event) => {
			event.preventDefault();
			const vin = core.normalizeVin(input.value);
			input.value = vin;
			showCheck(root, input);
			if (!core.isValidVin(vin) && !core.isChassisNumber(vin)) {
				input.setAttribute("aria-invalid", "true");
				setStatus(root, MESSAGES.invalid, "error");
				input.focus();
				return;
			}
			input.removeAttribute("aria-invalid");
			const visitor = form.querySelector("input[name=name]");
			const name = core.normalizeName(visitor.value);
			if (!name) {
				visitor.setAttribute("aria-invalid", "true");
				setStatus(root, MESSAGES.name, "error");
				visitor.focus();
				return;
			}
			visitor.removeAttribute("aria-invalid");
			tell(root, vin, name).catch(() => setStatus(root, MESSAGES.failed, "error"));
		});
	}

	document.querySelectorAll(".vst").forEach(mount);
})();
