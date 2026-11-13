/* The sleep test, line for line the same as pipeline/sleep.py.
   site/test.html runs this against the same real-account fixture as the Python tests. */
const SleepCore = (() => {
  const CONFIG = { minDays: 5, machineMaxGap: 2, machineMinHoursPerDay: 8, timerMaxHours: 3, minHours: 6, minGap: 5, maxGap: 14 };

  function union(dayMasks) {
    return dayMasks.reduce((all, mask) => all | mask, 0);
  }

  function bits(mask) {
    let n = 0;
    for (let h = 0; h < 24; h++) n += (mask >> h) & 1;
    return n;
  }

  /* Longest run of empty hours on the 24-hour clock: [gap, midpoint hour]. */
  function longestQuiet(hourMask) {
    const hours = [];
    for (let h = 0; h < 24; h++) if ((hourMask >> h) & 1) hours.push(h);
    if (!hours.length) return [24, 0];
    let bestGap = -1, bestStart = 0;
    hours.forEach((h, i) => {
      const next = i + 1 < hours.length ? hours[i + 1] : hours[0] + 24;
      const gap = next - h - 1;
      if (gap > bestGap) { bestGap = gap; bestStart = h; }
    });
    return [bestGap, (bestStart + 1 + bestGap / 2) % 24];
  }

  function classify(dayMasks, crit) {
    const nDays = dayMasks.length;
    const hourMask = union(dayMasks);
    const nHours = bits(hourMask);
    const nSlots = dayMasks.reduce((sum, mask) => sum + bits(mask), 0);
    const [gap, mid] = longestQuiet(hourMask);
    const hoursPerDay = nDays ? nSlots / nDays : 0;
    const significant = gap >= CONFIG.minGap && gap >= crit[nHours];
    let label;
    if (nDays < CONFIG.minDays) label = "too_few";
    else if (gap <= CONFIG.machineMaxGap && hoursPerDay >= CONFIG.machineMinHoursPerDay) label = "machine";
    else if (nHours <= CONFIG.timerMaxHours) label = "timer";
    else if (significant && gap <= CONFIG.maxGap && nHours >= CONFIG.minHours) label = "sleeper";
    else if (significant) label = "routine";
    else label = "unclear";
    return { class: label, n_days: nDays, n_hours: nHours, n_slots: nSlots, gap, mid, hours_per_day: hoursPerDay };
  }

  return { union, longestQuiet, classify, CONFIG };
})();
if (typeof module !== "undefined") module.exports = SleepCore;
