type LocalParts = { year: number; month: number; day: number; hour: number; minute: number };

function formatter(timeZone: string) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  });
}

function partsAt(instant: number, format: Intl.DateTimeFormat): LocalParts {
  const values = Object.fromEntries(format.formatToParts(instant).map((part) => [part.type, Number(part.value)]));
  return { year: values.year, month: values.month, day: values.day, hour: values.hour, minute: values.minute };
}

function sameParts(first: LocalParts, second: LocalParts) {
  return first.year === second.year && first.month === second.month && first.day === second.day &&
    first.hour === second.hour && first.minute === second.minute;
}

export function clubDate(instant: Date, timeZone: string) {
  const { year, month, day } = partsAt(instant.getTime(), formatter(timeZone));
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function nextClubDate(date: string) {
  return new Date(Date.parse(`${date}T00:00:00Z`) + 86_400_000).toISOString().slice(0, 10);
}

export function clubLocalToIso(date: string, time: string, timeZone: string) {
  const [year, month, day] = date.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const desired = { year, month, day, hour, minute };
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  const format = formatter(timeZone);
  const offsets = new Set([-36, -12, 0, 12, 36].map((hours) => {
    const sample = guess + hours * 3_600_000;
    const local = partsAt(sample, format);
    return Date.UTC(local.year, local.month - 1, local.day, local.hour, local.minute) - sample;
  }));
  const matches = [...offsets]
    .map((offset) => guess - offset)
    .filter((instant) => sameParts(partsAt(instant, format), desired));
  if (matches.length !== 1) {
    throw new Error(matches.length ? "This club time occurs twice. Choose another time." : "This club time does not exist. Choose another time.");
  }
  return new Date(matches[0]).toISOString();
}
