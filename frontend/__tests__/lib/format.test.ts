import {
  formatDollars,
  formatPct,
  formatROAS,
  formatPValue,
  isSignificant,
} from "@/lib/format";

describe("formatDollars", () => {
  it("formats a positive dollar amount", () => {
    expect(formatDollars(117500)).toBe("$117,500");
  });
  it("formats zero", () => {
    expect(formatDollars(0)).toBe("$0");
  });
  it("returns em dash for null", () => {
    expect(formatDollars(null)).toBe("—");
  });
  it("returns em dash for undefined", () => {
    expect(formatDollars(undefined)).toBe("—");
  });
  it("rounds to whole dollars", () => {
    expect(formatDollars(1234.99)).toBe("$1,235");
  });
});

describe("formatPct", () => {
  it("formats a proportion as percentage", () => {
    expect(formatPct(0.153)).toBe("15.3%");
  });
  it("formats zero", () => {
    expect(formatPct(0)).toBe("0.0%");
  });
  it("returns em dash for null", () => {
    expect(formatPct(null)).toBe("—");
  });
  it("respects custom decimal places", () => {
    expect(formatPct(0.12345, 2)).toBe("12.35%");
  });
  it("handles negative proportions", () => {
    expect(formatPct(-0.05)).toBe("-5.0%");
  });
});

describe("formatROAS", () => {
  it("formats a ROAS value with x suffix", () => {
    expect(formatROAS(2.35)).toBe("2.35x");
  });
  it("returns em dash for null", () => {
    expect(formatROAS(null)).toBe("—");
  });
  it("formats to 2 decimal places", () => {
    expect(formatROAS(3)).toBe("3.00x");
  });
});

describe("formatPValue", () => {
  it("formats a p-value to 3 decimal places", () => {
    expect(formatPValue(0.023)).toBe("0.023");
  });
  it("shows < 0.001 for tiny p-values", () => {
    expect(formatPValue(0.0001)).toBe("< 0.001");
  });
  it("returns em dash for null", () => {
    expect(formatPValue(null)).toBe("—");
  });
  it("formats 0.05 correctly", () => {
    expect(formatPValue(0.05)).toBe("0.050");
  });
});

describe("isSignificant", () => {
  it("returns true for p < 0.05", () => {
    expect(isSignificant(0.049)).toBe(true);
  });
  it("returns false for p = 0.05", () => {
    expect(isSignificant(0.05)).toBe(false);
  });
  it("returns false for p > 0.05", () => {
    expect(isSignificant(0.1)).toBe(false);
  });
  it("returns false for null", () => {
    expect(isSignificant(null)).toBe(false);
  });
  it("returns false for undefined", () => {
    expect(isSignificant(undefined)).toBe(false);
  });
});
