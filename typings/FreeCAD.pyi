class Vector:
    x: float
    y: float
    z: float

    def __init__(self, x: float = ..., y: float = ..., z: float = ...) -> None: ...
    def __sub__(self, other: Vector) -> Vector: ...

    @property
    def Length(self) -> float: ...


class Placement:
    Base: Vector
    Rotation: object

    def __init__(self) -> None: ...
