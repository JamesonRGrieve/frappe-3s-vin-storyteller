// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller production statistics (/storyteller/stats): the pure part. Filters the API's facet rows
// ([year, model, region, value, cars]) and folds them into the series each chart draws. No DOM; exposes
// globalThis.VinStatsCore for stats.js and the Node unit tests.
(() => {
	"use strict";

	const YEAR = 0;
	const MODEL = 1;
	const REGION = 2;
	const VALUE = 3;
	const CARS = 4;
	// Fixed model order: a model keeps its colour slot whatever the filter (colour follows the entity).
	const MODEL_ORDER = Object.freeze(["3000GT", "Stealth", "GTO", "Other"]);
	const OTHER = "Other";
	const LOCALE = "en-CA";
	const FORMULA_START = /^[=+\-@\t\r]/; // a CSV cell a spreadsheet would run as a formula
	const YEAR_PATTERN = /^(19|20)[0-9]{2}$/;
	const STATE_KEYS = Object.freeze(["model", "market", "region", "from", "to"]);

	function formatNumber(n) {
		return Number(n).toLocaleString(LOCALE);
	}

	function percent(count, total) {
		if (!total) return "0%";
		const share = (100 * count) / total;
		return `${share < 1 && share > 0 ? share.toFixed(1) : Math.round(share)}%`;
	}

	function modelSlot(model) {
		const slot = MODEL_ORDER.indexOf(model);
		return slot === -1 ? MODEL_ORDER.length - 1 : slot;
	}

	function orderedModels(models) {
		return [...models].sort((a, b) => modelSlot(a) - modelSlot(b) || a.localeCompare(b));
	}

	// A filter: models, markets and regions are arrays of names (empty = every one); from/to bound the model year.
	function emptyFilter() {
		return { model: [], market: [], region: [], from: "", to: "" };
	}

	// Which rows a filter keeps, as a predicate over a facet row.
	function rowTest(stats, filter) {
		const models = new Set(filter.model);
		const markets = new Set(filter.market);
		const regions = new Set(filter.region);
		const from = Number(filter.from) || -Infinity;
		const to = Number(filter.to) || Infinity;
		const keepYear = stats.years.map((year) => {
			const n = Number(year);
			return Number.isNaN(n) ? !filter.from && !filter.to : n >= from && n <= to;
		});
		const keepModel = stats.models.map((model) => !models.size || models.has(model));
		const keepRegion = stats.regions.map(
			(region) =>
				(!markets.size || markets.has(region.market)) && (!regions.size || regions.has(region.name)),
		);
		return (row) => keepYear[row[YEAR]] && keepModel[row[MODEL]] && keepRegion[row[REGION]];
	}

	function filtered(stats, facet, filter) {
		const keep = rowTest(stats, filter);
		return stats.facets[facet].rows.filter(keep);
	}

	function sumBy(rows, position) {
		const totals = new Map();
		for (const row of rows) totals.set(row[position], (totals.get(row[position]) || 0) + row[CARS]);
		return totals;
	}

	// The "line" facet counts every car exactly once, so it carries the totals by year, model and region.
	function totalRows(stats, filter) {
		return filtered(stats, "line", filter);
	}

	function summary(stats, filter) {
		const rows = totalRows(stats, filter);
		const total = rows.reduce((n, row) => n + row[CARS], 0);
		const distinct = (facet) => {
			const values = stats.facets[facet].values;
			return new Set(
				filtered(stats, facet, filter)
					.filter((row) => values[row[VALUE]].code !== "")
					.map((row) => row[VALUE]),
			).size;
		};
		const years = [...sumBy(rows, YEAR).keys()].map((i) => stats.years[i]).filter((y) => YEAR_PATTERN.test(y));
		years.sort();
		return {
			total,
			models: sumBy(rows, MODEL).size,
			regions: sumBy(rows, REGION).size,
			paints: distinct("paint"),
			interiors: distinct("interior"),
			firstYear: years[0] || "",
			lastYear: years[years.length - 1] || "",
		};
	}

	// Regions with their cars, most first: [{name, market, country, count}].
	function regionTotals(stats, filter) {
		const totals = sumBy(totalRows(stats, filter), REGION);
		return [...totals]
			.map(([i, count]) => ({ ...stats.regions[i], count }))
			.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
	}

	// Cars per world-map country, and the regions with no country on the map.
	function countryTotals(regions) {
		const countries = new Map();
		const unmapped = [];
		for (const region of regions) {
			if (region.country) countries.set(region.country, (countries.get(region.country) || 0) + region.count);
			else unmapped.push(region);
		}
		return { countries, unmapped };
	}

	// A facet's values with their cars, most first: [{index, value, count}].
	function facetTotals(stats, facet, filter) {
		const totals = sumBy(filtered(stats, facet, filter), VALUE);
		const values = stats.facets[facet].values;
		return [...totals]
			.map(([index, count]) => ({ index, value: values[index], count }))
			.sort((a, b) => b.count - a.count || label(a.value).localeCompare(label(b.value)));
	}

	function label(value) {
		if (value.paint !== undefined) return `${value.paint || "—"} / ${value.interior || "—"}`;
		if (value.code && value.name && value.code !== value.name) return `${value.code} ${value.name}`;
		return value.name || value.code || "";
	}

	// The first n entries, the rest folded into one "Other" entry (never a 9th colour).
	function topWithOther(entries, n) {
		if (entries.length <= n) return entries;
		const rest = entries.slice(n).reduce((sum, e) => sum + e.count, 0);
		return [...entries.slice(0, n), { index: -1, value: { name: OTHER, code: "" }, count: rest, other: true }];
	}

	// Model years present after filtering, in order.
	function yearAxis(stats, rows) {
		const present = new Set(rows.map((row) => row[YEAR]));
		return stats.years
			.map((year, index) => ({ year, index }))
			.filter((y) => present.has(y.index))
			.sort((a, b) => a.year.localeCompare(b.year));
	}

	// Cars per model year for each group a row belongs to: {years: ['1991', ...], series: [{key, data: [...]}]}.
	function seriesByYear(stats, rows, groupOf, groups) {
		const axis = yearAxis(stats, rows);
		const column = new Map(axis.map((y, i) => [y.index, i]));
		const series = new Map(groups.map((g) => [g, new Array(axis.length).fill(0)]));
		for (const row of rows) {
			const key = groupOf(row);
			if (series.has(key)) series.get(key)[column.get(row[YEAR])] += row[CARS];
		}
		return { years: axis.map((y) => y.year), series: groups.map((key) => ({ key, data: series.get(key) })) };
	}

	function modelsByYear(stats, filter) {
		const rows = totalRows(stats, filter);
		const present = orderedModels(new Set(rows.map((row) => stats.models[row[MODEL]])));
		return seriesByYear(stats, rows, (row) => stats.models[row[MODEL]], present);
	}

	// The top regions per model year (the rest as Other). The top is taken over every car, not the filtered ones, so
	// a region keeps its place, and its colour, whatever the filter: {years, series, slots: name -> colour slot}.
	function regionsByYear(stats, filter, top) {
		const rows = totalRows(stats, filter);
		const overall = regionTotals(stats, emptyFilter())
			.map((r) => r.name)
			.slice(0, top);
		const slots = new Map(overall.map((name, i) => [name, i]));
		const present = new Set(rows.map((row) => stats.regions[row[REGION]].name));
		const kept = new Set(overall.filter((name) => present.has(name)));
		const hasOther = [...present].some((name) => !kept.has(name));
		const groups = [...kept, ...(hasOther ? [OTHER] : [])];
		const result = seriesByYear(
			stats,
			rows,
			(row) => (kept.has(stats.regions[row[REGION]].name) ? stats.regions[row[REGION]].name : OTHER),
			groups,
		);
		return { ...result, slots };
	}

	// Each facet value's share of every model year's cars, for the top n values (the rest as Other).
	function facetShareByYear(stats, facet, filter, top) {
		const rows = filtered(stats, facet, filter);
		const ranked = facetTotals(stats, facet, filter).map((e) => e.index);
		const kept = new Set(ranked.slice(0, top));
		const groups = ranked.length > top ? [...ranked.slice(0, top), -1] : ranked;
		const result = seriesByYear(stats, rows, (row) => (kept.has(row[VALUE]) ? row[VALUE] : -1), groups);
		const totals = result.years.map((_, i) => result.series.reduce((n, s) => n + s.data[i], 0));
		return {
			years: result.years,
			series: result.series.map((s) => ({
				key: s.key,
				value: s.key === -1 ? { name: OTHER, code: "" } : stats.facets[facet].values[s.key],
				data: s.data,
				share: s.data.map((n, i) => (totals[i] ? (100 * n) / totals[i] : 0)),
			})),
		};
	}

	// Cars per calendar build month for each model: {months: ['1990-05', ...], series: [{key, data}]}.
	function monthsByModel(stats, filter) {
		const rows = filtered(stats, "month", filter);
		const values = stats.facets.month.values;
		const months = [...new Set(rows.map((row) => values[row[VALUE]].code).filter(Boolean))].sort();
		const column = new Map(months.map((m, i) => [m, i]));
		const models = orderedModels(new Set(rows.map((row) => stats.models[row[MODEL]])));
		const series = new Map(models.map((m) => [m, new Array(months.length).fill(0)]));
		for (const row of rows) {
			const month = values[row[VALUE]].code;
			if (month) series.get(stats.models[row[MODEL]])[column.get(month)] += row[CARS];
		}
		return { months, series: models.map((key) => ({ key, data: series.get(key) })) };
	}

	// Paint x interior: the top paints and interiors and the cars built in each pair.
	function colourMatrix(stats, filter, topPaints, topInteriors) {
		const rows = filtered(stats, "colours", filter);
		const values = stats.facets.colours.values;
		const paintTotals = new Map();
		const interiorTotals = new Map();
		const pairs = new Map();
		for (const row of rows) {
			const { paint, interior } = values[row[VALUE]];
			if (!paint || !interior) continue;
			paintTotals.set(paint, (paintTotals.get(paint) || 0) + row[CARS]);
			interiorTotals.set(interior, (interiorTotals.get(interior) || 0) + row[CARS]);
			const key = `${paint}|${interior}`;
			pairs.set(key, (pairs.get(key) || 0) + row[CARS]);
		}
		const top = (totals, n) =>
			[...totals]
				.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
				.slice(0, n)
				.map(([code]) => code);
		const paints = top(paintTotals, topPaints);
		const interiors = top(interiorTotals, topInteriors);
		const cells = [];
		let max = 0;
		paints.forEach((paint, x) =>
			interiors.forEach((interior, y) => {
				const n = pairs.get(`${paint}|${interior}`) || 0;
				if (n) cells.push([x, y, n]);
				max = Math.max(max, n);
			}),
		);
		return { paints, interiors, cells, max };
	}

	// Market -> region -> model, for a sunburst.
	function marketTree(stats, filter) {
		const markets = new Map();
		for (const row of totalRows(stats, filter)) {
			const region = stats.regions[row[REGION]];
			const model = stats.models[row[MODEL]];
			const market = markets.get(region.market) || new Map();
			markets.set(region.market, market);
			const models = market.get(region.name) || new Map();
			market.set(region.name, models);
			models.set(model, (models.get(model) || 0) + row[CARS]);
		}
		const byValue = (a, b) => b.value - a.value || a.name.localeCompare(b.name);
		return [...markets]
			.map(([name, regions]) => {
				const children = [...regions]
					.map(([regionName, models]) => {
						const leaves = orderedModels(models.keys()).map((m) => ({ name: m, value: models.get(m), model: m }));
						return { name: regionName, value: leaves.reduce((n, l) => n + l.value, 0), children: leaves };
					})
					.sort(byValue);
				return { name, value: children.reduce((n, c) => n + c.value, 0), children };
			})
			.sort(byValue);
	}

	// Rarity tiers in their order, rarest first.
	function rarityTotals(stats, filter) {
		return facetTotals(stats, "rarity", filter).sort((a, b) => a.value.order - b.value.order);
	}

	// The facts a reader asks first: the commonest and scarcest paint, the regions with the most and fewest cars, and
	// the cars per generation. Unrecorded paints never count as a paint.
	function highlights(stats, filter) {
		const paints = facetTotals(stats, "paint", filter).filter((e) => e.value.code);
		const regions = regionTotals(stats, filter);
		const generations = facetTotals(stats, "generation", filter).sort((a, b) =>
			a.value.name.localeCompare(b.value.name),
		);
		const scarcest = paints.length ? paints[paints.length - 1].count : 0;
		return {
			commonestPaint: paints[0] || null,
			scarcestPaints: paints.filter((e) => e.count === scarcest),
			mostRegion: regions[0] || null,
			fewestRegion: regions.length > 1 ? regions[regions.length - 1] : null,
			generations,
		};
	}

	// Option items by region: each item's share of the region's cars whose option contents are on record.
	// {items: [{index, value, count}], regions: [{name, of}], cells: [[item, region, share, cars]]}
	function optionsByRegion(stats, filter, top) {
		const known = stats.facets.option_records.values.findIndex((v) => v.code === "on_record");
		const denominators = new Map();
		for (const row of filtered(stats, "option_records", filter)) {
			if (row[VALUE] === known)
				denominators.set(row[REGION], (denominators.get(row[REGION]) || 0) + row[CARS]);
		}
		const regions = [...denominators]
			.sort((a, b) => b[1] - a[1])
			.map(([index, of]) => ({ index, name: stats.regions[index].name, of }));
		const items = facetTotals(stats, "options", filter).slice(0, top);
		const itemColumn = new Map(items.map((e, i) => [e.index, i]));
		const regionRow = new Map(regions.map((r, i) => [r.index, i]));
		const cars = new Map();
		for (const row of filtered(stats, "options", filter)) {
			if (!itemColumn.has(row[VALUE]) || !regionRow.has(row[REGION])) continue;
			const key = `${itemColumn.get(row[VALUE])}|${regionRow.get(row[REGION])}`;
			cars.set(key, (cars.get(key) || 0) + row[CARS]);
		}
		const cells = [...cars].map(([key, n]) => {
			const [x, y] = key.split("|").map(Number);
			return [x, y, Math.round((1000 * n) / regions[y].of) / 10, n];
		});
		return { items, regions, cells };
	}

	// One option item's cars in each region, against the region's cars with option contents on record.
	function itemByRegion(stats, filter, itemIndex) {
		const { regions } = optionsByRegion(stats, filter, 0);
		const cars = new Map();
		for (const row of filtered(stats, "options", filter)) {
			if (row[VALUE] === itemIndex) cars.set(row[REGION], (cars.get(row[REGION]) || 0) + row[CARS]);
		}
		return regions
			.map((r) => ({ name: r.name, of: r.of, count: cars.get(r.index) || 0 }))
			.filter((r) => r.count)
			.sort((a, b) => b.count / b.of - a.count / a.of || b.count - a.count);
	}

	// Rows whose text matches every word of a search, case-insensitively.
	function searchRows(rows, query) {
		const words = String(query || "")
			.toLowerCase()
			.split(/\s+/)
			.filter(Boolean);
		if (!words.length) return rows;
		return rows.filter((row) => {
			const text = row.join(" ").toLowerCase();
			return words.every((w) => text.includes(w));
		});
	}

	// Sort table rows by one column; numbers numerically, text alphabetically.
	function sortRows(rows, column, descending) {
		const sign = descending ? -1 : 1;
		return [...rows].sort((a, b) => {
			const x = a[column];
			const y = b[column];
			const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
			return sign * order;
		});
	}

	// --- car search -----------------------------------------------------------------------------------------------

	const PERIODS = { 0: "", 1: "1st period", 2: "2nd period", 3: "3rd period" };
	const SEARCH_COLUMNS = Object.freeze(["VIN", "Year", "Model line", "Region", "Paint", "Interior", "Option", "Built", "Source"]);

	// The search request: the page's filters plus the search form's text and codes, as API parameters.
	function searchParams(filter, fields, page) {
		const params = new URLSearchParams();
		const add = (key, value) => {
			const text = String(value || "").trim();
			if (text) params.set(key, text);
		};
		add("q", fields.q);
		if (fields.missing) params.set("missing", "1");
		add("paint", fields.paint);
		add("interior", fields.interior);
		add("option", fields.option);
		add("model", filter.model.join(","));
		add("market", filter.market.join(","));
		add("region", filter.region.join(","));
		add("from", filter.from);
		add("to", filter.to);
		add("line", fields.line);
		add("built_from", fields.built_from);
		add("built_to", fields.built_to);
		add("sort", fields.sort);
		if (fields.desc) params.set("desc", "1");
		if (page > 1) params.set("page", String(page));
		return params.toString();
	}

	// The search form's fields kept in the address (prefixed, so they never clash with the page filters), so a
	// search is shareable and the story can link straight to one (spec twins, build-date neighbours).
	const SEARCH_FIELDS = Object.freeze(["q", "paint", "interior", "option", "line", "built_from", "built_to", "sort"]);
	const FIELD_PATTERN = /^[A-Za-z0-9-]{1,17}$/;
	const SORT_TITLES = Object.freeze({
		"": "Model year",
		vin: "VIN",
		built: "Build date",
		paint: "Paint",
		interior: "Interior",
		option: "Option",
		grade: "Grade",
	});

	function parseSearch(search) {
		const params = new URLSearchParams(search || "");
		const fields = { missing: params.get("find_missing") === "1", desc: params.get("find_desc") === "1" };
		for (const name of SEARCH_FIELDS) {
			const value = (params.get(`find_${name}`) || "").trim();
			fields[name] = FIELD_PATTERN.test(value) ? value : "";
		}
		if (!(fields.sort in SORT_TITLES)) fields.sort = "";
		return fields;
	}

	function hasSearch(fields) {
		return Boolean(fields.missing || SEARCH_FIELDS.some((name) => name !== "sort" && fields[name]));
	}

	// The page address: the filters (stateQuery) plus the search fields, as find_<name>.
	function addressQuery(state, fields) {
		const params = new URLSearchParams(stateQuery(state).slice(1));
		if (fields && hasSearch(fields)) {
			for (const name of SEARCH_FIELDS) if (fields[name]) params.set(`find_${name}`, fields[name]);
			if (fields.missing) params.set("find_missing", "1");
			if (fields.desc) params.set("find_desc", "1");
		}
		const query = params.toString();
		return query ? `?${query}` : "";
	}

	// The search's breakdown panels, in display order, with their titles.
	const BREAKDOWN_TITLES = Object.freeze({
		paint: "Paint",
		interior: "Interior",
		line: "Model line",
		grade: "Grade",
		option: "Option code",
		model_year: "Model year",
		region: "Region",
	});

	// A breakdown value's label: its code and, where the catalogue names it, the name.
	function shareLabel(share) {
		if (share.code === "other") return "Other";
		if (!share.code) return "Not recorded";
		return share.name && share.name !== "MISSING" ? `${share.code} ${share.name}` : share.code;
	}

	// The form fields a click on a breakdown value narrows the search to (null when it can't narrow by it).
	function narrowBy(facet, share, fields) {
		if (!share.code || share.code === "other") return null;
		const code = share.code.split(" ")[1];
		if (facet === "paint" || facet === "interior") return { ...fields, [facet]: share.code };
		if (facet === "option" && code) return { ...fields, option: code };
		return null;
	}

	// The download of every matching car (the server's CSV, not just the page shown).
	function exportHref(endpoint, filter, fields) {
		return `${endpoint}?${searchParams(filter, fields, 1)}`;
	}

	// A stored 'YYMMP' build date as text: '92032' -> '1992-03, 2nd period'; month-only (P = 0) -> '1994-07'.
	function builtLabel(built) {
		const match = /^([0-9]{2})([0-9]{2})([0-3])$/.exec(String(built || ""));
		if (!match) return "";
		const year = Number(match[1]) < 50 ? `20${match[1]}` : `19${match[1]}`;
		const period = PERIODS[match[3]];
		return period ? `${year}-${match[2]}, ${period}` : `${year}-${match[2]}`;
	}

	// A found car's table cells, in SEARCH_COLUMNS order.
	function carCells(car) {
		return [
			car.vin,
			car.model_year,
			car.line,
			car.region,
			car.paint,
			car.interior,
			car.option,
			builtLabel(car.built),
			car.provenance,
		];
	}

	const TAG_ADDRESS = "lostvin@3shub.ca"; // lost-VIN reports (operator, 2026-11-12)
	const MARKET_NAMES = { us: "North America", au: "Australia" };

	// A missing range's table cells, in SEARCH_COLUMNS order: the VIN or range, its year, what is missing.
	function missingCells(entry) {
		const what = entry.count > 1 ? `${entry.count} serials missing` : "Missing from the factory records";
		return [entry.vin, entry.model_year, what, MARKET_NAMES[entry.market] || entry.market, "", "", "", "", entry.note];
	}

	// A mailto link asking the owner for a photo of the VIN tag, the VIN (or range) in the subject.
	function tagMailto(entry) {
		const subject = `VIN tag for ${entry.vin}`;
		const body = [
			`My car's VIN is ${entry.count > 1 ? "(please type it here)" : entry.vin}.`,
			"A photo of its VIN tag (dash plate or door sticker) is attached.",
			"Anything else I know about it (colour, options, history):",
		].join("\n");
		return `mailto:${TAG_ADDRESS}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
	}

	// --- the address: a filtered view is shareable -----------------------------------------------------------

	function parseState(search) {
		const params = new URLSearchParams(search || "");
		const state = emptyFilter();
		for (const key of ["model", "market", "region"]) {
			state[key] = params
				.getAll(key)
				.flatMap((v) => v.split(","))
				.map((v) => v.trim())
				.filter(Boolean);
		}
		for (const key of ["from", "to"]) {
			const year = (params.get(key) || "").trim();
			state[key] = YEAR_PATTERN.test(year) ? year : "";
		}
		return state;
	}

	function stateQuery(state) {
		const params = new URLSearchParams();
		for (const key of STATE_KEYS) {
			const value = state[key];
			if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
			else if (value) params.set(key, value);
		}
		const query = params.toString();
		return query ? `?${query}` : "";
	}

	// --- tables and CSV -----------------------------------------------------------------------------------------

	function csvCell(value) {
		let text = value === null || value === undefined ? "" : String(value);
		if (FORMULA_START.test(text)) text = `'${text}`;
		return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
	}

	function toCsv(header, rows) {
		return [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n");
	}

	// A facet's table: one row per value, with its cars and share of the filtered total.
	function facetTable(stats, facet, filter) {
		const entries = facetTotals(stats, facet, filter);
		const total = entries.reduce((n, e) => n + e.count, 0);
		const columns = facetColumns(facet);
		return {
			header: [...columns.map((c) => c.title), "Cars", "Share"],
			rows: entries.map((e) => [...columns.map((c) => e.value[c.key] ?? ""), e.count, percent(e.count, total)]),
		};
	}

	function facetColumns(facet) {
		if (facet === "colours")
			return [
				{ key: "paint", title: "Paint" },
				{ key: "interior", title: "Interior" },
			];
		if (facet === "paint" || facet === "interior" || facet === "options")
			return [
				{ key: "code", title: "Code" },
				{ key: "name", title: "Name" },
			];
		const titles = {
			line: "Model line",
			transmission: "Transmission",
			month: "Build month",
			rarity: "Exact-spec run",
			generation: "Generation",
			option_records: "Option contents",
		};
		return [{ key: "name", title: titles[facet] || "Value" }];
	}

	// Every filtered car group as flat rows: year, model, region, market, value, cars.
	function rawTable(stats, facet, filter) {
		const columns = facetColumns(facet);
		const values = stats.facets[facet].values;
		return {
			header: ["Model year", "Model", "Region", "Market", ...columns.map((c) => c.title), "Cars"],
			rows: filtered(stats, facet, filter).map((row) => {
				const region = stats.regions[row[REGION]];
				const value = values[row[VALUE]];
				return [
					stats.years[row[YEAR]],
					stats.models[row[MODEL]],
					region.name,
					region.market,
					...columns.map((c) => value[c.key] ?? ""),
					row[CARS],
				];
			}),
		};
	}

	globalThis.VinStatsCore = Object.freeze({
		MODEL_ORDER,
		OTHER,
		formatNumber,
		percent,
		modelSlot,
		orderedModels,
		emptyFilter,
		rowTest,
		summary,
		regionTotals,
		countryTotals,
		facetTotals,
		label,
		topWithOther,
		modelsByYear,
		regionsByYear,
		facetShareByYear,
		monthsByModel,
		colourMatrix,
		marketTree,
		rarityTotals,
		highlights,
		optionsByRegion,
		itemByRegion,
		searchRows,
		sortRows,
		SEARCH_COLUMNS,
		searchParams,
		builtLabel,
		carCells,
		missingCells,
		tagMailto,
		SEARCH_FIELDS,
		SORT_TITLES,
		BREAKDOWN_TITLES,
		parseSearch,
		hasSearch,
		addressQuery,
		shareLabel,
		narrowBy,
		exportHref,
		parseState,
		stateQuery,
		csvCell,
		toCsv,
		facetTable,
		rawTable,
	});
})();
