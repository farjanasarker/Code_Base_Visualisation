"""Unit tests for the class/interface/struct/trait extraction added in GoF
Phase 0 Step 1 (ParsedClass, ParsedField, class_name/is_method on
ParsedFunction). Exercises both the tree-sitter path (grammar installed,
the common case) and specifically checks the two multi-class/multi-impl
regex-fallback bugs the migration plan called out: Java's "first class in
file wins for every method" and Rust's "first impl in file wins for every
function" (and its `impl Trait for Type` mislabeling).
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from analyzer.parser import UniversalParser  # noqa: E402

parser = UniversalParser()


def _classes_by_name(classes):
    return {c.name: c for c in classes}


def _fns_by_name(functions):
    return {f.name: f for f in functions}


def test_python_class_bases_and_fields():
    src = """
from abc import ABC

class Shape(ABC):
    default_color: str = "black"

    def __init__(self, radius):
        self.radius = radius
        self.tags = []

    def area(self):
        return 0
"""
    functions, classes = parser.parse_file("shape.py", src, "python")
    cls = _classes_by_name(classes)["Shape"]
    assert cls.kind == "abstract_class"
    assert cls.bases == ["ABC"]
    field_names = {f.name for f in cls.fields}
    assert {"default_color", "radius", "tags"} <= field_names
    tags_field = next(f for f in cls.fields if f.name == "tags")
    assert tags_field.is_collection is True

    fns = _fns_by_name(functions)
    assert fns["area"].class_name == "Shape"
    assert fns["area"].is_method is True


def test_js_class_extends():
    src = """
class Animal {
  legs = 4;
}
class Dog extends Animal {
  bark() { return 1; }
}
"""
    functions, classes = parser.parse_file("animal.js", src, "javascript")
    by_name = _classes_by_name(classes)
    assert by_name["Dog"].bases == ["Animal"]
    fns = _fns_by_name(functions)
    assert fns["bark"].class_name == "Dog"
    assert fns["bark"].is_method is True


def test_ts_class_implements_and_interface():
    src = """
interface Shape {
  area(): number;
}
class Circle implements Shape {
  radius: number;
  area(): number { return 3.14 * this.radius * this.radius; }
}
abstract class Base {
  abstract go(): void;
}
"""
    functions, classes = parser.parse_file("shape.ts", src, "typescript")
    by_name = _classes_by_name(classes)
    assert by_name["Shape"].kind == "interface"
    assert by_name["Circle"].interfaces == ["Shape"]
    assert by_name["Base"].kind == "abstract_class"
    fns = _fns_by_name(functions)
    assert fns["area"].class_name == "Circle"

    radius_field = next(f for f in by_name["Circle"].fields if f.name == "radius")
    assert radius_field.type == "number", (
        "TS's `type:` field is the whole `type_annotation` node (`: number`) — "
        "must be stripped to a bare type name for HAS_FIELD resolution"
    )


def test_ts_class_extends_without_implements():
    """Regression check: capturing `(implements_clause) @implements_list` as
    a whole optional node was observed to silently drop the sibling optional
    `@superclass` capture whenever implements_clause itself is absent — i.e.
    any class with `extends` but no `implements`, which is the common case.
    Fixed by capturing `class_heritage` whole and walking its children in
    Python instead (`_parse_class_heritage`).
    """
    src = """
class Circle {
  radius: number;
}
class ScaledCircle extends Circle {
  factor: number;
}
"""
    functions, classes = parser.parse_file("shape.ts", src, "typescript")
    by_name = _classes_by_name(classes)
    assert by_name["ScaledCircle"].bases == ["Circle"]
    assert by_name["ScaledCircle"].interfaces == []


def test_java_multi_class_file_does_not_collapse():
    """Regression check: previously, a single `re.search` for the first
    `class` keyword in the file meant every method in a multi-class Java
    file was attributed to whichever class appeared first.
    """
    src = """
public class Base {
    public void baseMethod() { helper(); }
}

public class Derived extends Base {
    public void derivedMethod() { helper(); }
}
"""
    # Force the regex fallback path directly, since that's the code path
    # with the bug being regression-tested (tree-sitter succeeds and takes
    # a different path when the java grammar is installed).
    functions, classes = parser._parse_java_regex("multi.java", src)
    fns = _fns_by_name(functions)
    assert fns["baseMethod"].class_name == "Base"
    assert fns["derivedMethod"].class_name == "Derived"
    by_name = _classes_by_name(classes)
    assert by_name["Derived"].bases == ["Base"]


def test_java_tree_sitter_path_multi_class_and_interfaces():
    src = """
public interface Shape {
    double area();
}

public abstract class Base implements Shape {
    protected int sides;
}

public class Circle extends Base implements Shape {
    private double radius;
    public double area() { return 3.14 * radius * radius; }
}
"""
    functions, classes = parser.parse_file("shapes.java", src, "java")
    by_name = _classes_by_name(classes)
    assert by_name["Shape"].kind == "interface"
    assert by_name["Base"].kind == "abstract_class"
    assert by_name["Base"].interfaces == ["Shape"]
    assert by_name["Circle"].bases == ["Base"]
    assert by_name["Circle"].interfaces == ["Shape"]
    fns = _fns_by_name(functions)
    assert fns["area"].class_name == "Circle"


def test_go_struct_and_receiver_linkage():
    src = """
type Shape interface {
	Area() float64
}

type Circle struct {
	Radius float64
	Name   string
}

func (c *Circle) Area() float64 {
	return 3.14 * c.Radius * c.Radius
}
"""
    functions, classes = parser.parse_file("shape.go", src, "go")
    by_name = _classes_by_name(classes)
    assert by_name["Shape"].kind == "interface"
    assert by_name["Circle"].kind == "struct"
    field_names = {f.name for f in by_name["Circle"].fields}
    assert {"Radius", "Name"} <= field_names
    fns = _fns_by_name(functions)
    assert fns["Circle.Area"].class_name == "Circle"
    assert fns["Circle.Area"].is_method is True


def test_rust_multi_impl_file_does_not_collapse():
    """Regression check: previously, a single `.search()` for the first
    `impl` in the file meant every function in a multi-impl Rust file was
    attributed to whichever impl happened to appear first, and `impl Trait
    for Type` blocks were mislabeled with the trait's name instead of the
    type's.
    """
    src = """
pub trait Shape {
    fn area(&self) -> f64;
}

pub struct Circle {
    pub radius: f64,
}

pub struct Square {
    pub side: f64,
}

impl Shape for Circle {
    fn area(&self) -> f64 {
        3.14 * self.radius * self.radius
    }
}

impl Square {
    pub fn area(&self) -> f64 {
        self.side * self.side
    }
}
"""
    # Force the regex fallback path directly, mirroring the Java test above.
    functions, classes = parser._parse_rust_regex("shapes.rs", src)
    circle_area = [f for f in functions if f.name == "area" and f.class_name == "Circle"]
    square_area = [f for f in functions if f.name == "area" and f.class_name == "Square"]
    assert len(circle_area) == 1, "impl Trait for Type must resolve class_name to the Type, not the Trait"
    assert len(square_area) == 1, "each impl block's functions must not collapse onto the first impl in the file"

    by_name = _classes_by_name(classes)
    assert by_name["Circle"].kind == "struct"
    assert by_name["Square"].kind == "struct"
    assert by_name["Shape"].kind == "trait"


def test_rust_tree_sitter_path_impl_trait_for_type():
    src = """
pub trait Shape {
    fn area(&self) -> f64;
}
pub struct Circle {
    pub radius: f64,
}
impl Shape for Circle {
    fn area(&self) -> f64 {
        3.14 * self.radius * self.radius
    }
}
"""
    functions, classes = parser.parse_file("shape.rs", src, "rust")
    fns = _fns_by_name(functions)
    assert fns["area"].class_name == "Circle"
    by_name = _classes_by_name(classes)
    assert by_name["Circle"].kind == "struct"
    assert by_name["Shape"].kind == "trait", "the trait declaration itself is still a real class entry"
    field_names = {f.name for f in by_name["Circle"].fields}
    assert "radius" in field_names


def test_interface_method_signatures_counted_without_bodies():
    """Regression check: interface/trait method *signatures* have no body,
    so they never produce a Function/METHOD_OF node — `ParsedClass.method_names`
    must still count them directly from the declaration, or predicates like
    Strategy's "interface with exactly one method" have nothing to count.
    """
    ts_src = "interface Shape { area(): number; perimeter(): number; }"
    _fns, ts_classes = parser.parse_file("shape.ts", ts_src, "typescript")
    assert _classes_by_name(ts_classes)["Shape"].method_names == ["area", "perimeter"]

    java_src = "interface Shape { double area(); double perimeter(); }"
    _fns, java_classes = parser.parse_file("shape.java", java_src, "java")
    assert _classes_by_name(java_classes)["Shape"].method_names == ["area", "perimeter"]

    go_src = "type Shape interface { Area() float64; Perimeter() float64 }"
    _fns, go_classes = parser.parse_file("shape.go", go_src, "go")
    assert _classes_by_name(go_classes)["Shape"].method_names == ["Area", "Perimeter"]

    rust_src = "trait Shape { fn area(&self) -> f64; fn perimeter(&self) -> f64; }"
    _fns, rust_classes = parser.parse_file("shape.rs", rust_src, "rust")
    assert _classes_by_name(rust_classes)["Shape"].method_names == ["area", "perimeter"]

    py_src = """
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self): ...
    @abstractmethod
    def perimeter(self): ...
"""
    _fns, py_classes = parser.parse_file("shape.py", py_src, "python")
    assert _classes_by_name(py_classes)["Shape"].method_names == ["area", "perimeter"]


def test_java_class_without_implements_still_matches():
    """Regression check: `interfaces: (super_interfaces)` without a `?` made
    the whole class_declaration pattern fail to match any class that doesn't
    implement anything — i.e. most classes.
    """
    src = """
public class Plain {
    public void doWork() {}
}
"""
    functions, classes = parser.parse_file("plain.java", src, "java")
    by_name = _classes_by_name(classes)
    assert "Plain" in by_name
    assert by_name["Plain"].interfaces == []
    fns = _fns_by_name(functions)
    assert fns["doWork"].class_name == "Plain"
