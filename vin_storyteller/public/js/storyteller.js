// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller front end: asks the storyteller API for a VIN's story and renders it as text nodes only.
// Pure helpers live in storyteller-core.js (globalThis.VinStorytellerCore), loaded first.
(() => {
	"use strict";

	const core = globalThis.VinStorytellerCore;
	const MESSAGES = {
		invalid: "Please enter a valid 17 character VIN. VINs never contain the letters I, O or Q.",
		busy: "Reading the production record…",
		failed: "The storyteller is unavailable right now. Please try again later.",
		limited: "You've told a lot of stories in a short time. Please try again later.",
	};
	const HTTP_TOO_MANY_REQUESTS = 429;

	function element(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined) node.textContent = text;
		return node;
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
		result.querySelector(".vst-built").textContent = `Built in ${story.built}.`;

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
			specRow("Model year", story.model_year),
			specRow("Manufacturer", story.manufacturer),
			specRow("Model", story.model),
			specRow("Trim", story.trim || "—"),
			specRow("Exterior colour", core.codedText(story.exterior)),
			specRow("Interior colour", core.codedText(story.interior)),
			specRow("Equipment", core.codedText(story.equipment)),
			specRow("VIN", story.vin),
		);
		result.querySelector(".vst-provenance").textContent = core.provenanceText(story.provenance);

		const history = result.querySelector(".vst-history");
		history.querySelector(".vst-history-list").replaceChildren(...story.history.map(historyItem));
		history.hidden = story.history.length === 0;

		result.hidden = false;
		result.focus();
	}

	async function tell(root, vin) {
		const status = root.querySelector(".vst-status");
		const result = root.querySelector(".vst-result");
		const button = root.querySelector("button[type=submit]");
		result.hidden = true;
		status.textContent = MESSAGES.busy;
		button.disabled = true;
		try {
			const url = `${root.dataset.endpoint}?vin=${encodeURIComponent(vin)}`;
			const response = await fetch(url, { headers: { Accept: "application/json" } });
			if (response.status === HTTP_TOO_MANY_REQUESTS) {
				status.textContent = MESSAGES.limited;
				return;
			}
			if (!response.ok) {
				status.textContent = MESSAGES.failed;
				return;
			}
			const { message: reply } = await response.json();
			if (reply.status === "found") {
				status.textContent = "";
				render(root, reply.story);
			} else {
				status.textContent = reply.message || MESSAGES.failed;
			}
		} catch {
			status.textContent = MESSAGES.failed;
		} finally {
			button.disabled = false;
		}
	}

	function mount(root) {
		const form = root.querySelector(".vst-form");
		const input = form.querySelector("input[name=vin]");
		form.addEventListener("submit", (event) => {
			event.preventDefault();
			const vin = core.normalizeVin(input.value);
			input.value = vin;
			if (!core.isValidVin(vin)) {
				input.setAttribute("aria-invalid", "true");
				root.querySelector(".vst-status").textContent = MESSAGES.invalid;
				input.focus();
				return;
			}
			input.removeAttribute("aria-invalid");
			tell(root, vin).catch(() => {
				root.querySelector(".vst-status").textContent = MESSAGES.failed;
			});
		});
	}

	document.querySelectorAll(".vst").forEach(mount);
})();
