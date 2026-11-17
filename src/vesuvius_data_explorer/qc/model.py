"""Immutable, interface-independent QC results in ZYX coordinates."""
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Literal, Mapping

Status = Literal['pass', 'warn', 'fail', 'error', 'skipped']
STATUSES = ('pass', 'warn', 'fail', 'error', 'skipped')


@dataclass(frozen=True)
class Location:
    level: str
    axis: str
    index: int
    origin: tuple[int, int]
    size: tuple[int, int]

    def __post_init__(self):
        if self.axis not in ('z', 'y', 'x') or self.index < 0:
            raise ValueError('Localisation ZYX invalide.')
        if len(self.origin) != 2 or len(self.size) != 2:
            raise ValueError('Origine et taille doivent être 2D.')
        if any(n < 0 for n in self.origin) or any(n < 1 for n in self.size):
            raise ValueError('Fenêtre invalide.')
        object.__setattr__(self, 'origin', tuple(self.origin))
        object.__setattr__(self, 'size', tuple(self.size))

    def to_dict(self):
        return {'level': self.level, 'axis': self.axis, 'index': self.index,
                'origin': list(self.origin), 'size': list(self.size)}


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: Status
    value: float | None
    threshold: Mapping[str, float]
    message: str
    locations: tuple[Location, ...] = ()

    def __post_init__(self):
        if self.status not in STATUSES or (self.value is not None and not isfinite(self.value)):
            raise ValueError('Résultat QC invalide ou non fini.')
        if any(not isfinite(value) for value in self.threshold.values()):
            raise ValueError('Seuil non fini.')
        object.__setattr__(self, 'threshold', MappingProxyType(dict(self.threshold)))
        object.__setattr__(self, 'locations', tuple(self.locations))

    def to_dict(self):
        return {'check_id': self.check_id, 'status': self.status, 'value': self.value,
                'threshold': dict(self.threshold), 'message': self.message,
                'locations': [loc.to_dict() for loc in self.locations]}
