// SPDX-License-Identifier: AGPL-3.0-or-later
// VIN Storyteller: pure helpers (no DOM). Loaded as a plain script before storyteller.js, and by the
// Node unit tests; exposes globalThis.VinStorytellerCore.
(() => {
	"use strict";

	const VIN_PATTERN = /^[A-HJ-NPR-Z0-9]{17}$/;
	const SAFE_URL = /^https?:\/\/[^\s<>"']+$/i;
	const TIER_NAMES = {
		one_of_one: "One of one",
		sub10: "Fewer than 10",
		sub25: "Fewer than 25",
		sub50: "Fewer than 50",
		sub100: "Fewer than 100",
	};
	const HISTORY_KINDS = {
		auction: "Auction",
		photo: "Photos",
		sale: "Sale",
		registration: "Registration",
		service: "Service",
		article: "Article",
		other: "Record",
	};
	const PROVENANCE_NAMES = { CAPS: "the factory production record (CAPS export)" };
	const LOCALE = "en-CA";
	const VIN_LENGTH = 17;
	const LOOK_ALIKES = /[IOQ]/;
	const NOT_VIN_CHARACTER = /[^A-Z0-9]/;

	const normalizeVin = (raw) => String(raw ?? "").replace(/\s+/g, "").toUpperCase();
	const isValidVin = (vin) => VIN_PATTERN.test(vin);
	const isSafeUrl = (url) => typeof url === "string" && SAFE_URL.test(url);
	const formatNumber = (n) => Number(n).toLocaleString(LOCALE);
	const positionText = (p) => `No. ${formatNumber(p.position)} of ${formatNumber(p.total)}`;
	const UNDECODED = "MISSING"; // the record's placeholder for a code nobody has deciphered yet
	const codedText = (c) => (c.description === UNDECODED ? `Not yet decoded · ${c.code}` : `${c.description} · ${c.code}`);
	const provenanceText = (p) => `Production record source: ${PROVENANCE_NAMES[p] || p}.`;

	// Live feedback while typing: the count so far and, once something is wrong, why. `ready` means the VIN
	// can be looked up; nothing here blocks submitting (the submit handler validates again).
	function vinCheck(raw) {
		const vin = normalizeVin(raw);
		const count = `${vin.length} / ${VIN_LENGTH}`;
		if (NOT_VIN_CHARACTER.test(vin)) return { count, state: "bad", ready: false, message: "Use letters and numbers only." };
		if (LOOK_ALIKES.test(vin)) {
			return { count, state: "bad", ready: false, message: "VINs never contain I, O or Q. Did you mean 1 or 0?" };
		}
		if (vin.length > VIN_LENGTH) return { count, state: "bad", ready: false, message: `That's more than ${VIN_LENGTH} characters.` };
		if (vin.length === VIN_LENGTH) return { count, state: "ready", ready: true, message: "" };
		return { count, state: vin.length ? "typing" : "empty", ready: false, message: "" };
	}

	function badgeParts(rarity) {
		return {
			tier: TIER_NAMES[rarity.tier] || rarity.tier,
			count: `1 of ${formatNumber(rarity.total)}`,
			scope: rarity.description,
		};
	}

	function historyParts(record) {
		return {
			meta: [record.date, HISTORY_KINDS[record.kind] || HISTORY_KINDS.other].filter(Boolean).join(" · "),
			title: record.title,
			url: isSafeUrl(record.url) ? record.url : null,
			source: [record.source && `Source: ${record.source}`, record.provenance && `Added by: ${record.provenance}`]
				.filter(Boolean)
				.join(" · "),
		};
	}

	function timelineText(story) {
		return (
			`Production for the ${story.model_year} model year started in ${story.year_started}, and the first ` +
			`${story.vehicle_name} came off the line in ${story.model_started}. A production period is about one ` +
			"third of a month, or approximately 10 days."
		);
	}

	globalThis.VinStorytellerCore = Object.freeze({
		normalizeVin,
		isValidVin,
		vinCheck,
		isSafeUrl,
		formatNumber,
		positionText,
		codedText,
		provenanceText,
		badgeParts,
		historyParts,
		timelineText,
	});
})();
