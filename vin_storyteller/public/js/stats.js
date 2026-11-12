// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller production statistics (/storyteller/stats): the DOM part. Fetches the stats once, keeps the filter
// in the address, and redraws every chart (Apache ECharts, vendored) and the table when it changes. Pure helpers are
// in stats-core.js; page text is set with text nodes, and every value an ECharts tooltip shows (HTML) is escaped.
(() => {
	"use strict";

	const core = globalThis.VinStatsCore;
	const MESSAGES = {
		busy: "Counting the production record…",
		failed: "The production record is unavailable right now. Please try again later.",
		limited: "You've opened a lot of storyteller pages this hour. Please try again later.",
		empty: "No cars match these filters.",
		noCharts: "The charts couldn't load in this browser; the numbers are below.",
	};
	const HTTP_TOO_MANY_REQUESTS = 429;
	const TOP_REGIONS = 7; // + Other: never more than 8 colours
	const TOP_PAINT_SHARE = 7;
	const TOP_BARS = 25;
	const TOP_LINES = 25;
	const TOP_PAIR_PAINTS = 20;
	const TOP_PAIR_INTERIORS = 15;
	const TOP_OPTIONS = 30;
	const RESIZE_DELAY_MS = 120;
	const CODE = /^[A-Z0-9]{2,4}$/;
	const MISSING = "MISSING";
	const MAP_NAME = "vst-world";
	const MARKET_ORDER = ["North America", "Japan", "Export", "Australia"];
	const NOT_RECORDED_NOTES = {
		paint: "The record holds no paint code for these cars (CAPS writes EXT).",
		interior: "The record holds no interior code for these cars (CAPS writes INT).",
	};
	const NO_NAME_NOTE = "No name is on file for this code yet.";
	const NO_NAME = "name not on file";
	const PAINT_EDGE = "rgba(255, 255, 255, 0.35)"; // a hairline so black paints show on the navy surface
	const MAP_BANDS = [
		{ min: 100000, label: "100,000 or more" },
		{ min: 10000, max: 99999, label: "10,000–99,999" },
		{ min: 1000, max: 9999, label: "1,000–9,999" },
		{ min: 100, max: 999, label: "100–999" },
		{ min: 1, max: 99, label: "1–99" },
	];
	const RARITY_NOTE =
		"Cars sharing a car's exact specification: model year, model line, paint, interior and option code, within its own market. A one-of-one is the only car built so.";
	const OPTIONS_NOTE =
		"Each cell is the share of a region's cars whose option code includes the item, out of the region's cars whose option contents are in Mitsubishi's catalogues (Japanese GTOs and export 3000GTs; the catalogues hold no option contents for North American cars).";

	const reduceMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

	function element(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined) node.textContent = text;
		return node;
	}

	function escapeHtml(value) {
		return String(value ?? "").replace(
			/[&<>"']/g,
			(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
		);
	}

	function setStatus(root, text, tone = "notice") {
		const status = root.querySelector(".vst-status");
		status.textContent = text;
		status.dataset.tone = tone;
		status.hidden = !text;
	}

	// A (?) toggletip: the button reveals its note on click or keyboard, and the note is read out.
	function help(note) {
		const wrap = element("span", "vst-help");
		const button = element("button", "vst-help-button", "?");
		button.type = "button";
		button.setAttribute("aria-label", "What does this mean?");
		button.setAttribute("aria-expanded", "false");
		button.title = note;
		const bubble = element("span", "vst-help-note");
		bubble.setAttribute("role", "status");
		button.addEventListener("click", () => {
			const open = button.getAttribute("aria-expanded") !== "true";
			button.setAttribute("aria-expanded", String(open));
			bubble.textContent = open ? note : "";
		});
		button.addEventListener("keydown", (event) => {
			if (event.key === "Escape") {
				button.setAttribute("aria-expanded", "false");
				bubble.textContent = "";
			}
		});
		wrap.append(button, bubble);
		return wrap;
	}

	function css(root, name) {
		return getComputedStyle(root).getPropertyValue(name).trim();
	}

	function palette(root) {
		return {
			series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => css(root, `--vst-series-${i}`)),
			other: css(root, "--vst-other"),
			seqLow: css(root, "--vst-seq-low"),
			seqHigh: css(root, "--vst-seq-high"),
			text: css(root, "--vst-text"),
			soft: css(root, "--vst-soft"),
			grid: css(root, "--vst-grid"),
			surface: css(root, "--vst-surface"),
		};
	}

	function codeHref(kind, code) {
		return CODE.test(code || "") ? `/storyteller/${kind}?code=${encodeURIComponent(code)}` : null;
	}

	// --- ECharts scaffolding ----------------------------------------------------------------------------------------

	function baseOption(colours, extra) {
		return {
			backgroundColor: "transparent",
			animation: !reduceMotion,
			aria: { enabled: true, decal: { show: false } },
			textStyle: { color: colours.soft, fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" },
			grid: { left: 8, right: 24, top: 44, bottom: 8, containLabel: true },
			tooltip: {
				confine: true,
				backgroundColor: "#0a1132",
				borderColor: colours.grid,
				textStyle: { color: colours.text, fontSize: 13 },
				extraCssText: "max-width: 320px; white-space: normal; border-radius: 10px;",
			},
			toolbox: {
				right: 0,
				top: 0,
				iconStyle: { borderColor: colours.soft },
				emphasis: { iconStyle: { borderColor: colours.text } },
				feature: {
					dataView: { readOnly: true, title: "Data", lang: ["Data", "Close", "Refresh"] },
					restore: { title: "Reset" },
					saveAsImage: { title: "Save image", backgroundColor: colours.surface, pixelRatio: 2 },
				},
			},
			...extra,
		};
	}

	function axisStyle(colours) {
		return {
			axisLine: { lineStyle: { color: colours.grid } },
			axisTick: { show: false },
			axisLabel: { color: colours.soft },
			splitLine: { lineStyle: { color: colours.grid } },
		};
	}

	function legend(colours, extra = {}) {
		return { top: 30, left: 0, right: 0, type: "scroll", textStyle: { color: colours.soft }, pageTextStyle: { color: colours.soft }, ...extra };
	}

	// The map's bands, brightest for the most cars (sequential blue: near zero recedes toward the surface).
	function mapBand(colours, index) {
		const steps = [colours.seqHigh, "#86b6ef", "#3987e5", "#256abf", colours.seqLow];
		return steps[index];
	}

	function tooltipRows(title, rows, note) {
		const lines = rows.map(([label, value]) => `${escapeHtml(label)}: <b>${escapeHtml(value)}</b>`);
		return `<b>${escapeHtml(title)}</b><br>${lines.join("<br>")}${note ? `<br><span style="opacity:.8">${escapeHtml(note)}</span>` : ""}`;
	}

	// --- the page ---------------------------------------------------------------------------------------------------

	class StatsPage {
		constructor(root, stats, swatches, world) {
			this.root = root;
			this.stats = stats;
			this.swatches = swatches;
			this.colours = palette(root);
			this.charts = new Map();
			this.clicks = new Map(); // the latest click handler per chart (options are rebuilt on every filter)
			this.notice = "";
			this.filter = core.parseState(location.search);
			this.table = { facet: "paint", search: "", sort: null, descending: true };
			this.hasMap = Boolean(world && globalThis.topojson && globalThis.echarts);
			if (this.hasMap) {
				const countries = globalThis.topojson.feature(world, world.objects.countries);
				// No 3S was built for Antarctica; leaving it out gives the inhabited world the room.
				countries.features = countries.features.filter((f) => f.properties?.name !== "Antarctica");
				globalThis.echarts.registerMap(MAP_NAME, countries);
			}
		}

		start() {
			this.buildFilters();
			this.buildTable();
			this.buildOptionPicker();
			this.buildSearch();
			this.root.querySelector(".vst-stats-filters").hidden = false;
			this.root.querySelector(".vst-stats-body").hidden = false;
			this.render();
			let timer = 0;
			globalThis.addEventListener("resize", () => {
				clearTimeout(timer);
				timer = setTimeout(() => this.charts.forEach((chart) => chart.resize()), RESIZE_DELAY_MS);
			});
			globalThis.addEventListener("popstate", () => {
				this.filter = core.parseState(location.search);
				this.syncFilters();
				this.render();
			});
		}

		modelColour(model) {
			return this.colours.series[core.modelSlot(model)] || this.colours.other;
		}

		paintColour(code) {
			const hex = this.swatches?.paint?.[code]?.hex;
			return /^#[0-9a-f]{6}$/i.test(hex || "") ? hex : this.colours.other;
		}

		// --- filters ---

		buildFilters() {
			const form = this.root.querySelector(".vst-stats-filters");
			const models = form.querySelector(".vst-stats-models");
			for (const model of core.orderedModels(this.stats.models)) {
				const chip = element("label", "vst-stats-chip");
				const input = element("input");
				input.type = "checkbox";
				input.name = "model";
				input.value = model;
				const text = element("span", "", model);
				text.style.setProperty("--chip-colour", this.modelColour(model));
				chip.append(input, text);
				models.append(chip);
			}
			const markets = [...new Set(this.stats.regions.map((r) => r.market))].sort(
				(a, b) => MARKET_ORDER.indexOf(a) - MARKET_ORDER.indexOf(b),
			);
			const marketSelect = form.elements.market;
			for (const market of markets) marketSelect.append(new Option(market, market));
			const years = this.stats.years.filter((y) => /^[0-9]{4}$/.test(y)).sort();
			for (const name of ["from", "to"]) {
				for (const year of years) form.elements[name].append(new Option(year, year));
			}
			this.fillRegions();
			this.syncFilters();
			form.addEventListener("change", (event) => {
				if (event.target.name === "market") this.fillRegions();
				this.readFilters();
			});
			form.addEventListener("reset", (event) => {
				event.preventDefault();
				this.setFilter(core.emptyFilter());
			});
			form.addEventListener("submit", (event) => event.preventDefault());
		}

		fillRegions() {
			const form = this.root.querySelector(".vst-stats-filters");
			const select = form.elements.region;
			const market = form.elements.market.value;
			const current = select.value;
			select.replaceChildren(new Option("Every region", ""));
			const names = this.stats.regions
				.filter((r) => !market || r.market === market)
				.map((r) => r.name)
				.sort((a, b) => a.localeCompare(b));
			for (const name of names) select.append(new Option(name, name));
			select.value = names.includes(current) ? current : "";
		}

		readFilters() {
			const form = this.root.querySelector(".vst-stats-filters");
			const value = (name) => form.elements[name].value;
			this.setFilter({
				model: [...form.querySelectorAll('input[name="model"]:checked')].map((i) => i.value),
				market: value("market") ? [value("market")] : [],
				region: value("region") ? [value("region")] : [],
				from: value("from"),
				to: value("to"),
			});
		}

		setFilter(filter) {
			this.filter = filter;
			history.replaceState(null, "", `${location.pathname}${core.stateQuery(filter)}${location.hash}`);
			this.syncFilters();
			this.render();
			if (this.search?.active) this.runSearch(1);
		}

		syncFilters() {
			const form = this.root.querySelector(".vst-stats-filters");
			form.querySelectorAll('input[name="model"]').forEach((input) => {
				input.checked = this.filter.model.includes(input.value);
			});
			form.elements.market.value = this.filter.market[0] || "";
			this.fillRegions();
			form.elements.region.value = this.filter.region[0] || "";
			form.elements.from.value = this.filter.from;
			form.elements.to.value = this.filter.to;
			const extra = [...this.filter.market.slice(1), ...this.filter.region.slice(1)];
			form.querySelector(".vst-stats-filter-note").textContent = extra.length
				? `Also filtered to: ${extra.join(", ")} (from the address).`
				: "";
		}

		toggleRegion(name) {
			const region = this.filter.region.includes(name) ? [] : [name];
			this.setFilter({ ...this.filter, region });
		}

		// --- drawing ---

		render() {
			const summary = core.summary(this.stats, this.filter);
			this.renderTiles(summary);
			const empty = summary.total === 0;
			setStatus(this.root, empty ? MESSAGES.empty : this.notice, "notice");
			const draw = {
				regions: () => this.regionsChart(),
				map: () => this.mapChart(),
				markets: () => this.marketsChart(),
				regionYears: () => this.regionYearsChart(),
				years: () => this.yearsChart(),
				rarity: () => this.rarityChart(),
				months: () => this.monthsChart(),
				paints: () => this.codeBars("paint"),
				interiors: () => this.codeBars("interior"),
				paintYears: () => this.paintYearsChart(),
				transmissionYears: () => this.facetYearsChart("transmission"),
				colours: () => this.coloursChart(),
				lines: () => this.linesChart(),
				options: () => this.optionsChart(),
				option: () => this.optionChart(),
			};
			for (const [name, build] of Object.entries(draw)) {
				const figure = this.root.querySelector(`[data-chart="${name}"]`);
				if (!figure) continue;
				const option = empty ? null : build();
				this.draw(figure, name, option);
			}
			this.renderTable();
		}

		draw(figure, name, option) {
			const plot = figure.querySelector(".vst-chart-plot");
			let chart = this.charts.get(name);
			if (!option) {
				chart?.dispose();
				this.charts.delete(name);
				plot.replaceChildren(element("p", "vst-chart-empty", MESSAGES.empty));
				return;
			}
			if (!chart) {
				plot.replaceChildren();
				chart = globalThis.echarts.init(plot, null, { renderer: "canvas" });
				this.charts.set(name, chart);
				chart.on("click", (params) => this.clicks.get(name)?.(params));
			}
			const { onClick, ...rest } = option;
			this.clicks.set(name, onClick);
			chart.setOption(rest, { notMerge: true });
		}

		renderTiles(summary) {
			const list = this.root.querySelector(".vst-stats-tiles");
			list.replaceChildren();
			const tile = (value, label, note) => {
				const item = element("li");
				item.append(element("span", "vst-n", value));
				const caption = element("span", "vst-l", label);
				if (note) caption.append(" ", help(note));
				item.append(caption);
				list.append(item);
			};
			tile(core.formatNumber(summary.total), "cars on record");
			if (summary.firstYear)
				tile(
					summary.firstYear === summary.lastYear ? summary.firstYear : `${summary.firstYear}–${summary.lastYear}`,
					"model years",
				);
			tile(core.formatNumber(summary.regions), "regions", "Markets and destinations the factory records name.");
			tile(core.formatNumber(summary.paints), "paint codes", "A paint's earlier \"A\"-form codes count as the same paint.");
			tile(core.formatNumber(summary.interiors), "interior codes");
			if (!summary.total) return;
			const h = core.highlights(this.stats, this.filter);
			for (const g of h.generations) {
				tile(core.formatNumber(g.count), g.value.name, "Split at the 1994 model year facelift (fixed headlamps).");
			}
			if (h.commonestPaint) {
				const p = h.commonestPaint;
				tile(p.value.code, `top paint: ${this.paintName(p.value)}, ${core.formatNumber(p.count)} cars`);
			}
			if (h.scarcestPaints.length) {
				const p = h.scarcestPaints;
				const names = p.slice(0, 3).map((e) => `${e.value.code} ${this.paintName(e.value)}`);
				const more = p.length > 3 ? ` and ${p.length - 3} more` : "";
				tile(
					core.formatNumber(p[0].count),
					`${p[0].count === 1 ? "car" : "cars"} in the scarcest ${p.length > 1 ? "paints" : "paint"}: ${names.join("; ")}${more}`,
				);
			}
			if (h.mostRegion) tile(core.formatNumber(h.mostRegion.count), `cars for ${h.mostRegion.name}, the most of any region`, h.mostRegion.note);
			if (h.fewestRegion) tile(core.formatNumber(h.fewestRegion.count), `cars for ${h.fewestRegion.name}, the fewest`, h.fewestRegion.note);
		}

		// A category axis label's width: its full width on a wide screen, a third of the page on a phone.
		labelWidth(widest) {
			return Math.min(widest, Math.round(this.root.clientWidth / 3));
		}

		paintName(value) {
			return value.name && value.name !== MISSING ? value.name : NO_NAME;
		}

		regionsChart() {
			const regions = core.regionTotals(this.stats, this.filter);
			const total = regions.reduce((n, r) => n + r.count, 0);
			const c = this.colours;
			const selected = new Set(this.filter.region);
			return baseOption(c, {
				grid: { left: 8, right: 56, top: 36, bottom: 8, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => {
						const r = regions[regions.length - 1 - p.dataIndex];
						return tooltipRows(r.name, [["Cars", core.formatNumber(r.count)], ["Share", core.percent(r.count, total)], ["Market", r.market]], `${r.note} Click to ${selected.has(r.name) ? "clear the filter" : "filter to this region"}.`);
					},
				},
				xAxis: { type: "value", ...axisStyle(c), axisLabel: { show: false }, splitLine: { show: false } },
				yAxis: { type: "category", data: [...regions].reverse().map((r) => r.name), ...axisStyle(c), axisLabel: { color: c.text, width: this.labelWidth(190), overflow: "truncate" } },
				series: [
					{
						type: "bar",
						barMaxWidth: 16,
						showBackground: true,
						backgroundStyle: { color: c.grid, borderRadius: 4 },
						itemStyle: { borderRadius: [0, 4, 4, 0] },
						label: { show: true, position: "right", color: c.text, formatter: (p) => core.formatNumber(p.value) },
						data: [...regions].reverse().map((r) => ({
							value: r.count,
							itemStyle: { color: selected.size && !selected.has(r.name) ? c.other : c.series[0] },
						})),
					},
				],
				onClick: (p) => this.toggleRegion([...regions].reverse()[p.dataIndex].name),
			});
		}

		mapChart() {
			const figure = this.root.querySelector('[data-chart="map"]');
			const note = figure.querySelector(".vst-chart-unmapped");
			if (!this.hasMap) {
				note.hidden = false;
				note.textContent = "The map couldn't load; the regions chart has the same numbers.";
				return null;
			}
			const regions = core.regionTotals(this.stats, this.filter);
			const { countries, unmapped } = core.countryTotals(regions);
			note.hidden = !unmapped.length;
			note.textContent = unmapped.length
				? `Not on the map: ${unmapped.map((r) => `${r.name} (${core.formatNumber(r.count)})`).join(", ")}.`
				: "";
			const byCountry = new Map();
			for (const r of regions) if (r.country) byCountry.set(r.country, [...(byCountry.get(r.country) || []), r]);
			const c = this.colours;
			return baseOption(c, {
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => {
						const parts = byCountry.get(p.name);
						if (!parts) return tooltipRows(p.name, [["Cars", "none on record"]]);
						return tooltipRows(p.name, parts.map((r) => [r.name, core.formatNumber(r.count)]));
					},
				},
				visualMap: {
					type: "piecewise",
					pieces: MAP_BANDS.map((band, i) => ({ ...band, color: mapBand(c, i) })),
					left: 0,
					bottom: 0,
					itemWidth: 14,
					itemHeight: 10,
					textStyle: { color: c.soft },
				},
				series: [
					{
						type: "map",
						map: MAP_NAME,
						roam: true,
						layoutCenter: ["50%", "50%"],
						layoutSize: "112%",
						scaleLimit: { min: 0.8, max: 12 },
						itemStyle: { areaColor: "#1a2350", borderColor: c.surface, borderWidth: 0.5 },
						emphasis: { label: { show: false }, itemStyle: { areaColor: c.series[1] } },
						select: { disabled: true },
						data: [...countries].map(([name, value]) => ({ name, value })),
					},
				],
			});
		}

		marketsChart() {
			const tree = core.marketTree(this.stats, this.filter);
			const c = this.colours;
			const ring = ["#2b3a7a", "#34478f"];
			const paint = (nodes, depth) =>
				nodes.map((n) => ({
					...n,
					itemStyle: { color: n.model ? this.modelColour(n.model) : ring[depth % ring.length], borderColor: c.surface, borderWidth: 2 },
					children: n.children ? paint(n.children, depth + 1) : undefined,
				}));
			return baseOption(c, {
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => tooltipRows(p.treePathInfo.slice(1).map((t) => t.name).join(" › "), [["Cars", core.formatNumber(p.value)]]),
				},
				series: [
					{
						type: "sunburst",
						radius: ["12%", "92%"],
						center: ["50%", "54%"],
						sort: null,
						nodeClick: "rootToNode",
						label: { color: c.text, minAngle: 12, overflow: "truncate", width: 90 },
						levels: [{}, { label: { rotate: 0 } }, { label: { rotate: "tangential" } }, { label: { show: false } }],
						data: paint(tree, 0),
					},
				],
			});
		}

		lineChart(years, series, colourOf, extra = {}) {
			const c = this.colours;
			return baseOption(c, {
				legend: legend(c),
				grid: { left: 8, right: 24, top: 72, bottom: 8, containLabel: true },
				tooltip: { ...baseOption(c).tooltip, trigger: "axis", valueFormatter: (v) => core.formatNumber(v) },
				xAxis: { type: "category", data: years, boundaryGap: false, ...axisStyle(c), splitLine: { show: false } },
				yAxis: { type: "value", ...axisStyle(c) },
				series: series.map((s) => ({
					name: s.key,
					type: "line",
					data: s.data,
					symbolSize: 8,
					lineStyle: { width: 2 },
					itemStyle: { color: colourOf(s.key), borderColor: c.surface, borderWidth: 2 },
					emphasis: { focus: "series" },
				})),
				...extra,
			});
		}

		yearsChart() {
			const { years, series } = core.modelsByYear(this.stats, this.filter);
			const option = this.lineChart(years, series, (m) => this.modelColour(m));
			option.toolbox.feature.magicType = { type: ["line", "bar", "stack"], title: { line: "Lines", bar: "Bars", stack: "Stack" } };
			return option;
		}

		regionYearsChart() {
			const { years, series, slots } = core.regionsByYear(this.stats, this.filter, TOP_REGIONS);
			return this.lineChart(years, series, (key) => (slots.has(key) ? this.colours.series[slots.get(key)] : this.colours.other));
		}

		monthsChart() {
			const { months, series } = core.monthsByModel(this.stats, this.filter);
			if (!months.length) return null;
			const option = this.lineChart(months, series, (m) => this.modelColour(m), {
				dataZoom: [
					{ type: "inside", start: 0, end: 100 },
					{ type: "slider", height: 22, bottom: 4, borderColor: this.colours.grid, textStyle: { color: this.colours.soft } },
				],
			});
			option.grid = { ...option.grid, bottom: 40 };
			option.series = option.series.map((s) => ({ ...s, symbol: "none", stack: "cars", areaStyle: { opacity: 0.35 } }));
			option.toolbox.feature.dataZoom = { title: { zoom: "Zoom", back: "Undo zoom" } };
			return option;
		}

		rarityChart() {
			const tiers = core.rarityTotals(this.stats, this.filter);
			const total = tiers.reduce((n, t) => n + t.count, 0);
			const c = this.colours;
			const ramp = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]; // ordinal: rarest brightest
			return baseOption(c, {
				grid: { left: 8, right: 24, top: 64, bottom: 8, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => tooltipRows(tiers[p.dataIndex].value.name, [["Cars", core.formatNumber(p.value)], ["Share", core.percent(p.value, total)]], RARITY_NOTE),
				},
				xAxis: { type: "category", data: tiers.map((t) => t.value.name), ...axisStyle(c), axisLabel: { color: c.text, interval: 0, width: 80, overflow: "break" } },
				yAxis: { type: "value", ...axisStyle(c) },
				series: [
					{
						type: "bar",
						barMaxWidth: 40,
						itemStyle: { borderRadius: [4, 4, 0, 0] },
						label: { show: true, position: "top", color: c.text, formatter: (p) => core.formatNumber(p.value) },
						data: tiers.map((t) => ({ value: t.count, itemStyle: { color: ramp[t.value.order] || c.other } })),
					},
				],
			});
		}

		codeBars(facet) {
			const entries = core.facetTotals(this.stats, facet, this.filter).slice(0, TOP_BARS).reverse();
			const total = core.facetTotals(this.stats, facet, this.filter).reduce((n, e) => n + e.count, 0);
			const c = this.colours;
			const name = (v) => (v.code ? `${v.code} ${v.name === MISSING ? "" : v.name}`.trim() : v.name);
			const noteOf = (v) => (!v.code ? NOT_RECORDED_NOTES[facet] : v.name === MISSING ? NO_NAME_NOTE : "") + (codeHref(facet, v.code) ? " Click for this code's page." : "");
			return baseOption(c, {
				grid: { left: 8, right: 56, top: 36, bottom: 8, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => {
						const e = entries[p.dataIndex];
						const swatch = facet === "paint" ? this.swatches?.paint?.[e.value.code] : null;
						const rows = [["Cars", core.formatNumber(e.count)], ["Share", core.percent(e.count, total)]];
						if (swatch?.finish) rows.push(["Finish", swatch.finish]);
						if (swatch?.dodge_name && swatch.dodge_name !== swatch.mitsubishi_name) rows.push(["Dodge's name", swatch.dodge_name]);
						return tooltipRows(name(e.value), rows, noteOf(e.value).trim());
					},
				},
				xAxis: { type: "value", ...axisStyle(c), axisLabel: { show: false }, splitLine: { show: false } },
				yAxis: { type: "category", data: entries.map((e) => name(e.value)), ...axisStyle(c), axisLabel: { color: c.text, width: this.labelWidth(200), overflow: "truncate", interval: 0 } },
				series: [
					{
						type: "bar",
						barMaxWidth: 14,
						showBackground: true,
						backgroundStyle: { color: c.grid, borderRadius: 4 },
						itemStyle: { borderRadius: [0, 4, 4, 0] },
						label: { show: true, position: "right", color: c.text, formatter: (p) => core.formatNumber(p.value) },
						data: entries.map((e) => ({
							value: e.count,
							itemStyle:
								facet === "paint" && e.value.code
									? { color: this.paintColour(e.value.code), borderColor: PAINT_EDGE, borderWidth: 1 }
									: { color: e.value.code ? c.series[0] : c.other },
						})),
					},
				],
				onClick: (p) => {
					const href = codeHref(facet, entries[p.dataIndex]?.value.code);
					if (href) location.assign(href);
				},
			});
		}

		stackedYears(result, colourOf, nameOf, percent) {
			const c = this.colours;
			return baseOption(c, {
				legend: legend(c),
				grid: { left: 8, right: 24, top: 72, bottom: 8, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "axis",
					axisPointer: { type: "shadow" },
					valueFormatter: (v) => (percent ? `${Number(v).toFixed(1)}%` : core.formatNumber(v)),
				},
				xAxis: { type: "category", data: result.years, ...axisStyle(c), splitLine: { show: false } },
				yAxis: { type: "value", max: percent ? 100 : undefined, ...axisStyle(c), axisLabel: { color: c.soft, formatter: percent ? "{value}%" : undefined } },
				series: result.series.map((s) => ({
					name: nameOf(s),
					type: "bar",
					stack: "share",
					barMaxWidth: 36,
					data: percent ? s.share.map((v) => Math.round(v * 10) / 10) : s.data,
					itemStyle: { color: colourOf(s), borderColor: percent ? PAINT_EDGE : c.surface, borderWidth: 1 },
					emphasis: { focus: "series" },
				})),
			});
		}

		paintYearsChart() {
			const result = core.facetShareByYear(this.stats, "paint", this.filter, TOP_PAINT_SHARE);
			return this.stackedYears(
				result,
				(s) => (s.key === -1 || !s.value.code ? this.colours.other : this.paintColour(s.value.code)),
				(s) => (s.value.code ? `${s.value.code} ${s.value.name === MISSING ? "" : s.value.name}`.trim() : s.value.name),
				true,
			);
		}

		facetYearsChart(facet) {
			const result = core.facetShareByYear(this.stats, facet, this.filter, TOP_REGIONS);
			const names = this.stats.facets[facet].values.map((v) => v.name).sort();
			return this.stackedYears(
				result,
				(s) => (s.key === -1 || s.value.name === "Not recorded" ? this.colours.other : this.colours.series[names.indexOf(s.value.name) % 8]),
				(s) => s.value.name,
				false,
			);
		}

		coloursChart() {
			const m = core.colourMatrix(this.stats, this.filter, TOP_PAIR_PAINTS, TOP_PAIR_INTERIORS);
			if (!m.cells.length) return null;
			const c = this.colours;
			const names = this.stats.facets.paint.values;
			const paintName = (code) => names.find((v) => v.code === code)?.name;
			const interiorName = (code) => this.stats.facets.interior.values.find((v) => v.code === code)?.name;
			const label = (code, name) => (name && name !== MISSING ? `${code} ${name}` : code);
			return baseOption(c, {
				grid: { left: 8, right: 16, top: 44, bottom: 64, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => {
						const [x, y, n] = p.data;
						return tooltipRows(`${label(m.paints[x], paintName(m.paints[x]))} with ${label(m.interiors[y], interiorName(m.interiors[y]))}`, [["Cars", core.formatNumber(n)]]);
					},
				},
				xAxis: { type: "category", data: m.paints, ...axisStyle(c), axisLabel: { color: c.text, interval: 0, rotate: 45 }, splitArea: { show: false } },
				yAxis: { type: "category", data: m.interiors, ...axisStyle(c), axisLabel: { color: c.text } },
				visualMap: { min: 0, max: m.max, orient: "horizontal", left: "center", bottom: 0, calculable: true, textStyle: { color: c.soft }, inRange: { color: [c.seqLow, c.seqHigh] } },
				series: [{ type: "heatmap", data: m.cells, itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: c.text } } }],
			});
		}

		linesChart() {
			const entries = core.facetTotals(this.stats, "line", this.filter).slice(0, TOP_LINES).reverse();
			const c = this.colours;
			const modelOf = (name) => core.MODEL_ORDER.find((m) => name.includes(m)) || core.OTHER;
			return baseOption(c, {
				grid: { left: 8, right: 56, top: 36, bottom: 8, containLabel: true },
				tooltip: { ...baseOption(c).tooltip, trigger: "item", formatter: (p) => tooltipRows(entries[p.dataIndex].value.name, [["Cars", core.formatNumber(p.value)]]) },
				xAxis: { type: "value", ...axisStyle(c), axisLabel: { show: false }, splitLine: { show: false } },
				yAxis: { type: "category", data: entries.map((e) => e.value.name), ...axisStyle(c), axisLabel: { color: c.text, width: this.labelWidth(260), overflow: "truncate" } },
				series: [
					{
						type: "bar",
						barMaxWidth: 14,
						itemStyle: { borderRadius: [0, 4, 4, 0] },
						label: { show: true, position: "right", color: c.text, formatter: (p) => core.formatNumber(p.value) },
						data: entries.map((e) => ({ value: e.count, itemStyle: { color: this.modelColour(modelOf(e.value.name)) } })),
					},
				],
			});
		}

		optionsChart() {
			const m = core.optionsByRegion(this.stats, this.filter, TOP_OPTIONS);
			if (!m.cells.length) return null;
			const c = this.colours;
			const itemLabel = (e) => `${e.value.code} ${e.value.name === MISSING ? "" : e.value.name}`.trim();
			return baseOption(c, {
				grid: { left: 8, right: 16, top: 44, bottom: 64, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => {
						const [x, y, share, n] = p.data;
						const region = m.regions[y];
						return tooltipRows(`${itemLabel(m.items[x])} · ${region.name}`, [["Share", `${share}%`], ["Cars", `${core.formatNumber(n)} of ${core.formatNumber(region.of)}`]]);
					},
				},
				xAxis: { type: "category", data: m.items.map((e) => e.value.code), ...axisStyle(c), axisLabel: { color: c.text, interval: 0, rotate: 60 } },
				yAxis: { type: "category", data: m.regions.map((r) => r.name), ...axisStyle(c), axisLabel: { color: c.text, width: this.labelWidth(180), overflow: "truncate" } },
				visualMap: { min: 0, max: 100, orient: "horizontal", left: "center", bottom: 0, calculable: true, text: ["100%", "0%"], textStyle: { color: c.soft }, inRange: { color: [c.seqLow, c.seqHigh] } },
				series: [{ type: "heatmap", data: m.cells, itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: c.text } } }],
				onClick: (p) => this.pickOption(m.items[p.data[0]].index),
			});
		}

		buildOptionPicker() {
			const select = this.root.querySelector('select[name="option"]');
			if (!select) return;
			const items = core.facetTotals(this.stats, "options", core.emptyFilter());
			const label = (v) => `${v.code} ${v.name === MISSING ? "(no text on file)" : v.name}`;
			items
				.slice()
				.sort((a, b) => label(a.value).localeCompare(label(b.value)))
				.forEach((e) => select.append(new Option(label(e.value), String(e.index))));
			const seats = items.find((e) => /SEAT HEATER|HEATED SEAT/i.test(e.value.name));
			select.value = String((seats || items[0])?.index ?? "");
			select.addEventListener("change", () => this.draw(this.root.querySelector('[data-chart="option"]'), "option", this.optionChart()));
			const note = this.root.querySelector(".vst-stats-options-note");
			if (note) note.append(" ", help(OPTIONS_NOTE));
		}

		pickOption(index) {
			const select = this.root.querySelector('select[name="option"]');
			if (!select) return;
			select.value = String(index);
			select.dispatchEvent(new Event("change"));
			select.focus();
		}

		optionChart() {
			const select = this.root.querySelector('select[name="option"]');
			if (!select?.value) return null;
			const rows = core.itemByRegion(this.stats, this.filter, Number(select.value));
			if (!rows.length) return null;
			const c = this.colours;
			const reversed = [...rows].reverse();
			return baseOption(c, {
				grid: { left: 8, right: 64, top: 36, bottom: 8, containLabel: true },
				tooltip: {
					...baseOption(c).tooltip,
					trigger: "item",
					formatter: (p) => {
						const r = reversed[p.dataIndex];
						return tooltipRows(r.name, [["Share", `${p.value}%`], ["Cars", `${core.formatNumber(r.count)} of ${core.formatNumber(r.of)}`]]);
					},
				},
				xAxis: { type: "value", max: 100, ...axisStyle(c), axisLabel: { color: c.soft, formatter: "{value}%" } },
				yAxis: { type: "category", data: reversed.map((r) => r.name), ...axisStyle(c), axisLabel: { color: c.text, width: this.labelWidth(190), overflow: "truncate" } },
				series: [
					{
						type: "bar",
						barMaxWidth: 16,
						showBackground: true,
						backgroundStyle: { color: c.grid, borderRadius: 4 },
						itemStyle: { color: c.series[0], borderRadius: [0, 4, 4, 0] },
						label: { show: true, position: "right", color: c.text, formatter: (p) => `${p.value}%` },
						data: reversed.map((r) => Math.round((1000 * r.count) / r.of) / 10),
					},
				],
			});
		}

		// --- car search ---

		buildSearch() {
			const section = this.root.querySelector(".vst-stats-search");
			if (!section) return;
			this.search = { active: false, page: 1, cars: [], section };
			const form = section.querySelector(".vst-stats-search-form");
			form.addEventListener("submit", (event) => {
				event.preventDefault();
				this.runSearch(1);
			});
			section.querySelector('[data-page="prev"]').addEventListener("click", () => this.runSearch(this.search.page - 1));
			section.querySelector('[data-page="next"]').addEventListener("click", () => this.runSearch(this.search.page + 1));
			section.querySelector(".vst-stats-search-csv").addEventListener("click", () => {
				const rows = this.search.cars.map((car) => core.carCells(car));
				const blob = new Blob([`\ufeff${core.toCsv(core.SEARCH_COLUMNS, rows)}`], { type: "text/csv;charset=utf-8" });
				const link = element("a");
				link.href = URL.createObjectURL(blob);
				link.download = `3s-cars-search-page-${this.search.page}.csv`;
				document.body.append(link);
				link.click();
				link.remove();
				setTimeout(() => URL.revokeObjectURL(link.href), 0);
			});
		}

		async runSearch(page) {
			const { section } = this.search;
			const form = section.querySelector(".vst-stats-search-form");
			const fields = Object.fromEntries(["q", "paint", "interior", "option"].map((n) => [n, form.elements[n].value]));
			fields.missing = form.elements.missing.checked;
			const status = section.querySelector(".vst-stats-search-status");
			const query = core.searchParams(this.filter, fields, page);
			this.search.active = true;
			status.textContent = MESSAGES.busy;
			let body;
			try {
				body = (await fetchJson(`${this.root.dataset.searchEndpoint}?${query}`)).message;
			} catch (error) {
				status.textContent = error.status === HTTP_TOO_MANY_REQUESTS ? MESSAGES.limited : MESSAGES.failed;
				return;
			}
			if (body?.status !== "found") {
				status.textContent = body?.message || MESSAGES.failed;
				this.showResults([], 0, 1, 1, false, [], 0);
				return;
			}
			this.showResults(body.cars, body.total, body.page, body.pages, body.truncated, body.missing || [], body.missing_total || 0);
		}

		showResults(cars, total, page, pages, truncated, missing = [], missingTotal = 0) {
			const { section } = this.search;
			this.search.cars = cars;
			this.search.page = page;
			const status = section.querySelector(".vst-stats-search-status");
			const parts = [];
			if (total || !missingTotal)
				parts.push(
					total
						? `${core.formatNumber(total)} ${total === 1 ? "car" : "cars"}${truncated ? " (search cut short: narrow it to see every match)" : ""}`
						: "No cars on record match",
				);
			if (missingTotal)
				parts.push(
					`${core.formatNumber(missingTotal)} missing ${missingTotal === 1 ? "range" : "ranges"} in red${missing.length < missingTotal ? ` (first ${missing.length} shown; narrow the filters for the rest)` : ""}`,
				);
			status.textContent = `${parts.join("; ")}.`;
			const table = section.querySelector(".vst-stats-results");
			const head = element("tr");
			for (const title of core.SEARCH_COLUMNS) {
				const th = element("th", "", title);
				th.scope = "col";
				head.append(th);
			}
			table.querySelector("thead").replaceChildren(head);
			table.querySelector("tbody").replaceChildren(
				...cars.map((car) => {
					const tr = element("tr");
					core.carCells(car).forEach((cell, i) => {
						const td = element(i === 0 ? "th" : "td");
						if (i === 0) td.scope = "row";
						const href =
							i === 0
								? `/storyteller?vin=${encodeURIComponent(car.vin)}`
								: i === 4
									? codeHref("paint", cell)
									: i === 5
										? codeHref("interior", cell)
										: null;
						if (href) {
							const link = element("a", "", cell);
							link.href = href;
							td.append(link);
						} else td.textContent = cell;
						tr.append(td);
					});
					return tr;
				}),
			);
			table.querySelector("tbody").append(
				...missing.map((entry) => {
					const tr = element("tr", "vst-missing");
					core.missingCells(entry).forEach((cell, i) => {
						const td = element(i === 0 ? "th" : "td");
						if (i === 0) td.scope = "row";
						if (i === 4) {
							const link = element("a", "", "Send your VIN tag");
							link.href = core.tagMailto(entry);
							td.colSpan = 4;
							td.append(link);
						} else if (i > 4 && i < 8) return;
						else td.textContent = cell;
						tr.append(td);
					});
					return tr;
				}),
			);
			section.querySelector(".vst-stats-table-wrap").hidden = !cars.length && !missing.length;
			section.querySelector(".vst-stats-search-csv").hidden = !cars.length;
			const pager = section.querySelector(".vst-stats-pager");
			pager.hidden = pages <= 1;
			pager.querySelector(".vst-stats-page-label").textContent = `Page ${page} of ${pages}`;
			pager.querySelector('[data-page="prev"]').disabled = page <= 1;
			pager.querySelector('[data-page="next"]').disabled = page >= pages;
		}

		// --- the numbers ---

		buildTable() {
			const section = this.root.querySelector(".vst-stats-data");
			section.querySelector('select[name="facet"]').addEventListener("change", (event) => {
				this.table = { ...this.table, facet: event.target.value, sort: null, descending: true };
				this.renderTable();
			});
			section.querySelector('input[name="search"]').addEventListener("input", (event) => {
				this.table.search = event.target.value;
				this.renderTable();
			});
			section.querySelectorAll(".vst-stats-csv").forEach((button) =>
				button.addEventListener("click", () => this.download(button.dataset.table)),
			);
		}

		tableData() {
			const { header, rows } = core.facetTable(this.stats, this.table.facet, this.filter);
			let shown = core.searchRows(rows, this.table.search);
			if (this.table.sort !== null) shown = core.sortRows(shown, this.table.sort, this.table.descending);
			return { header, rows: shown };
		}

		renderTable() {
			const table = this.root.querySelector(".vst-stats-data .vst-stats-table");
			const { header, rows } = this.tableData();
			const head = element("tr");
			header.forEach((title, i) => {
				const th = element("th");
				th.scope = "col";
				const numeric = title === "Cars" || title === "Share";
				if (numeric) th.className = "vst-num";
				if (this.table.sort === i) th.setAttribute("aria-sort", this.table.descending ? "descending" : "ascending");
				const button = element("button", "", title);
				button.type = "button";
				button.addEventListener("click", () => {
					const sortColumn = title === "Share" ? header.indexOf("Cars") : i;
					this.table.descending = this.table.sort === sortColumn ? !this.table.descending : numeric;
					this.table.sort = sortColumn;
					this.renderTable();
				});
				th.append(button);
				head.append(th);
			});
			table.querySelector("thead").replaceChildren(head);
			const body = table.querySelector("tbody");
			body.replaceChildren(
				...rows.map((row) => {
					const tr = element("tr");
					row.forEach((cell, i) => {
						const td = element(i === 0 ? "th" : "td", typeof cell === "number" || header[i] === "Share" ? "vst-num" : "");
						if (i === 0) td.scope = "row";
						const kind = this.table.facet === "paint" || this.table.facet === "interior" ? this.table.facet : null;
						const href = kind && i === 0 ? codeHref(kind, cell) : null;
						if (href) {
							const link = element("a", "", cell);
							link.href = href;
							td.append(link);
						} else td.textContent = typeof cell === "number" ? core.formatNumber(cell) : cell === MISSING ? NO_NAME : cell;
						tr.append(td);
					});
					return tr;
				}),
			);
			if (!rows.length) {
				const tr = element("tr");
				const td = element("td", "", MESSAGES.empty);
				td.colSpan = header.length;
				tr.append(td);
				body.append(tr);
			}
		}

		download(which) {
			const { header, rows } = which === "raw" ? core.rawTable(this.stats, this.table.facet, this.filter) : this.tableData();
			const blob = new Blob([`﻿${core.toCsv(header, rows)}`], { type: "text/csv;charset=utf-8" });
			const link = element("a");
			link.href = URL.createObjectURL(blob);
			link.download = `3s-production-${this.table.facet}${which === "raw" ? "-groups" : ""}.csv`;
			document.body.append(link);
			link.click();
			link.remove();
			setTimeout(() => URL.revokeObjectURL(link.href), 0);
		}
	}

	async function fetchJson(url) {
		const response = await fetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
		if (!response.ok) {
			const error = new Error(String(response.status));
			error.status = response.status;
			throw error;
		}
		return response.json();
	}

	async function optional(url) {
		try {
			return url ? await fetchJson(url) : null;
		} catch {
			return null; // swatch colours and the map are extras; the page works without them
		}
	}

	async function start(root) {
		setStatus(root, MESSAGES.busy, "busy");
		let body;
		try {
			body = (await fetchJson(root.dataset.statsEndpoint)).message;
		} catch (error) {
			setStatus(root, error.status === HTTP_TOO_MANY_REQUESTS ? MESSAGES.limited : MESSAGES.failed, "error");
			return;
		}
		if (body?.status !== "found") {
			setStatus(root, body?.message || MESSAGES.failed, "error");
			return;
		}
		const [swatches, world] = await Promise.all([optional(root.dataset.swatches), optional(root.dataset.world)]);
		setStatus(root, "");
		const page = new StatsPage(root, body.stats, swatches, world);
		if (!globalThis.echarts) {
			// Without the chart library the totals, highlights and table still work.
			page.notice = MESSAGES.noCharts;
			page.draw = () => {};
			root.querySelectorAll(".vst-chart").forEach((figure) => {
				figure.hidden = true;
			});
		}
		page.start();
	}

	function boot() {
		document.querySelectorAll(".vst-production[data-stats-endpoint]").forEach((root) => start(root));
	}

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
	else boot();
})();
