from tools.docs.architecture.imports import edges, layer


def test_core_imports_only_core():
    outside = [
        (source, target)
        for source, target, _ in sorted(edges())
        if layer(source) == "Core" and layer(target) != "Core"
    ]
    assert outside == []


def test_adapters_import_no_plumbing():
    upward = [
        (source, target)
        for source, target, _ in sorted(edges())
        if layer(source) == "Adapters" and layer(target) == "Plumbing"
    ]
    assert upward == []


def test_every_module_has_a_layer():
    for source, target, _ in edges():
        layer(source)
        layer(target)
