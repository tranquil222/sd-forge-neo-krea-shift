"""Job-local Shift experiments. Curve progress is independent of Shift's log scale."""
from dataclasses import dataclass
import math

FIXED = "Fixed"
VALUES = "One image per value"
RAMP = "Change during sampling"
CURVES = ("Linear", "Smooth ease in/out", "Ease in", "Ease out",
          "Logarithmic", "Exponential", "Reverse exponential", "Hold then switch")


def shift_value(value):
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError("Enter a numeric Krea Shift between 0 and 24.") from None
    if not math.isfinite(value) or not 0 <= value <= 24:
        raise ValueError("Krea Shift must be a finite mu value between 0 and 24.")
    return value


def parse_values(text):
    parts = str(text or "").split(",")
    if any(not item.strip() for item in parts):
        raise ValueError("Enter comma-separated Shift values, e.g. 0.5, 0.65, 1.15. Remove empty entries.")
    return tuple(shift_value(item.strip()) for item in parts)


@dataclass(frozen=True)
class Options:
    mode: str = FIXED
    values: str = ""
    start: float = 0.5
    end: float = 1.15
    curve: str = "Linear"
    switch: float = 50.0
    hires: bool = False
    multiple: bool = False
    fixed: float | None = None
    hr_fixed: float | None = None
    enabled: bool = True  # Legacy API calls predate the panel's enable checkbox.

    @property
    def run_multiple(self):
        # Retain support for 0.2 API requests, not a mutually exclusive UI mode.
        return self.enabled and (self.multiple or self.mode == VALUES)

    @classmethod
    def read(cls, *args):
        if not args:
            return cls(enabled=False)
        if len(args) == 11:
            *args, enabled = args
            if not enabled:
                # Disabled panels must not validate or run a stale/empty list.
                return cls(enabled=False)
        if len(args) == 7:
            mode, values, start, end, curve, switch, hires = args
            if mode not in (FIXED, VALUES, RAMP):
                raise ValueError("Choose a valid Krea2 Shift mode.")
            multiple, changing = mode == VALUES, mode == RAMP
            fixed = hr_fixed = None
        elif len(args) == 10:
            fixed, multiple, values, changing, start, end, curve, switch, hires, hr_fixed = args
        else:
            raise ValueError("Krea2 Shift controls changed. Restart Forge and refresh the browser.")
        if multiple:
            parse_values(values)
        if not changing:
            return cls(multiple=bool(multiple), values=str(values) if multiple else "",
                       fixed=shift_value(fixed) if fixed is not None else None,
                       hr_fixed=shift_value(hr_fixed) if hr_fixed is not None else None)
        if curve not in CURVES:
            raise ValueError("Choose a valid Shift transition curve.")
        switch = float(switch)
        if not math.isfinite(switch) or not 0 <= switch <= 100:
            raise ValueError("Shift switch point must be between 0 and 100 percent.")
        return cls(mode=RAMP, values=str(values) if multiple else "",
                   start=shift_value(start), end=shift_value(end), curve=curve, switch=switch,
                   hires=bool(hires), multiple=bool(multiple),
                   fixed=shift_value(fixed) if fixed is not None else None,
                   hr_fixed=shift_value(hr_fixed) if hr_fixed is not None else None)

    def progression(self, count):
        if count < 1:
            return []
        if count == 1:
            return [self.start]
        values = []
        for i in range(count):
            t = i / (count - 1)
            if self.curve == "Smooth ease in/out":
                t = t * t * (3 - 2 * t)
            elif self.curve == "Ease in":
                t *= t
            elif self.curve == "Ease out":
                t = 1 - (1 - t) ** 2
            elif self.curve == "Logarithmic":
                t = math.log1p(9 * t) / math.log(10)
            elif self.curve == "Exponential":
                t = math.expm1(math.log(10) * t) / 9
            elif self.curve == "Reverse exponential":
                t = -math.expm1(-math.log(10) * t) / .9
            elif self.curve == "Hold then switch":
                t = float(t >= self.switch / 100)
            values.append(self.start + (self.end - self.start) * t)
        values[0], values[-1] = self.start, self.end
        return values


def blend_intervals(grids, shifts, start_index=0):
    """Choose each step's interval from its Shift grid, then normalize its span.

    Directly splicing sigma points can make noise INCREASE at a transition.
    Blending positive intervals avoids that. Equal endpoints reproduce the native
    schedule exactly. For img2img, keep the starting noise and ramp only the suffix
    actually sampled. This is an experimental schedule, not a changing CFG/model.
    """
    import torch
    base = grids[shifts[0]]
    if len(shifts) != len(base) - 1 - start_index:
        raise ValueError("Krea Shift ramp does not match the sampler's step count.")
    if all(mu == shifts[0] for mu in shifts):
        return base.clone()
    widths = []
    for step, mu in enumerate(shifts, start_index):
        grid = grids[mu]
        if len(grid) != len(base):
            raise ValueError("This scheduler changes step count with Shift; ramp is unavailable.")
        widths.append((grid[step].double() - grid[step + 1].double()))
    widths = torch.stack(widths)
    if not torch.isfinite(widths).all() or (widths < 0).any() or widths.sum() <= 0:
        raise ValueError("Krea Shift ramp needs a finite, descending noise schedule.")
    span = base[start_index].double() - base[-1].double()
    tail = base[start_index].double() - torch.cumsum(widths / widths.sum() * span, dim=0)
    result = base.clone()
    result[start_index + 1:] = tail.to(result)
    result[-1] = base[-1]
    return result


def metadata(options, shifts, hires=False):
    result = {"Krea Shift enabled": options.enabled,
              "Krea Shift mode": options.mode if options.enabled else "Off"}
    if options.hr_fixed is not None:
        result["Krea Shift hires fixed"] = options.hr_fixed
    if not options.enabled or options.mode != RAMP:
        return result
    result.update({"Krea Shift from": options.start,
              "Krea Shift to": options.end, "Krea Shift curve": options.curve,
              "Krea Shift switch": options.switch, "Krea Shift hires": options.hires,
              "Krea Shift algorithm": "interval-v1"})
    result["Hires Krea Shift steps" if hires else "Krea Shift steps"] = ", ".join(f"{v:.8g}" for v in shifts)
    return result
