"""Unit tests for the Go/Rust Singleton language-idiom scanner
(patterns/language_idioms/singleton_idioms.py) — pure text-pattern
matching, no Neo4j required.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from patterns.language_idioms.singleton_idioms import scan_file, scan_files  # noqa: E402


def test_go_sync_once_detected():
    src = """
package config

import "sync"

var once sync.Once
var instance *Config

func GetInstance() *Config {
	once.Do(func() {
		instance = &Config{}
	})
	return instance
}
"""
    matches = scan_file("config.go", src, "go")
    assert len(matches) == 1
    assert matches[0]["idiom"] == "sync.Once"
    assert matches[0]["file"] == "config.go"
    assert matches[0]["line"] == 6


def test_go_without_sync_once_not_flagged():
    src = "package foo\n\nfunc GetInstance() {}\n"
    assert scan_file("foo.go", src, "go") == []


def test_rust_lazy_static_detected():
    src = """
use lazy_static::lazy_static;

lazy_static! {
    static ref CONFIG: Config = Config::new();
}
"""
    matches = scan_file("config.rs", src, "rust")
    assert any(m["idiom"] == "lazy_static!" for m in matches)


def test_rust_once_cell_detected():
    src = "static INSTANCE: OnceCell<Config> = OnceCell::new();\n"
    matches = scan_file("config.rs", src, "rust")
    assert any(m["idiom"] == "OnceCell" for m in matches)


def test_non_go_rust_language_ignored():
    assert scan_file("x.py", "sync.Once", "python") == []
    assert scan_file("x.ts", "lazy_static!", "typescript") == []


def test_scan_files_aggregates_across_files():
    files = [
        {"path": "a.go", "content": "sync.Once", "language": "go"},
        {"path": "b.rs", "content": "OnceLock<T>", "language": "rust"},
        {"path": "c.py", "content": "no idioms here", "language": "python"},
    ]
    matches = scan_files(files)
    assert {m["file"] for m in matches} == {"a.go", "b.rs"}
