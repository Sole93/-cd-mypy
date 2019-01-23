"""Top-level logic for the new semantic analyzer."""

from typing import List, Tuple, Optional, Union

from mypy.nodes import (
    Node, SymbolTable, SymbolNode, MypyFile, TypeInfo, FuncDef, Decorator, OverloadedFuncDef
)

MYPY = False
if MYPY:
    from mypy.build import Graph, State


def semantic_analysis_for_scc(graph: 'Graph', scc: List[str]) -> None:
    # Assume reachability analysis has already been performed.
    process_top_levels(graph, scc)
    process_functions(graph, scc)


def process_top_levels(graph: 'Graph', scc: List[str]) -> None:
    # Process top levels until everything has been bound.
    # TODO: Limit the number of iterations

    # Initialize ASTs and symbol tables.
    for id in scc:
        state = graph[id]
        assert state.tree is not None
        state.manager.new_semantic_analyzer.prepare_file(state.tree)

    # Initially all namespaces in the SCC are incomplete (well they are empty).
    state.manager.incomplete_namespaces.update(scc)

    worklist = scc[:]
    while worklist:
        deferred = []  # type: List[str]
        while worklist:
            next_id = worklist.pop()
            state = graph[next_id]
            assert state.tree is not None
            deferred += semantic_analyze_target(next_id, state, state.tree, None)
            # Assume this namespace is ready.
            # TODO: It could still be incomplete if some definitions couldn't be bound.
            state.manager.incomplete_namespaces.discard(next_id)
        worklist = deferred


def process_functions(graph: 'Graph', scc: List[str]) -> None:
    # TODO: This doesn't quite work yet
    # Process functions.
    deferred = []  # type: List[str]
    for module in scc:
        tree = graph[module].tree
        assert tree is not None
        symtable = tree.names
        targets = get_all_leaf_targets(symtable, module, None)
        for target, node, active_type in targets:
            deferred += semantic_analyze_target(target, graph[module], node, active_type)
    assert not deferred  # There can't be cross-function forward refs


TargetInfo = Tuple[str, Union[MypyFile, FuncDef], Optional[TypeInfo]]


def get_all_leaf_targets(symtable: SymbolTable,
                         prefix: str,
                         active_type: Optional[TypeInfo]) -> List[TargetInfo]:
    """Return all leaf targets in a symbol table (module-level and methods)."""
    result = []  # type: List[TargetInfo]
    for name, node in symtable.items():
        new_prefix = prefix + '.' + name
        # TODO: Decorated function
        # TODO: Overloaded function
        if isinstance(node.node, (FuncDef, TypeInfo)):
            if node.node.fullname() == new_prefix:
                if isinstance(node.node, TypeInfo):
                    result += get_all_leaf_targets(node.node.names, new_prefix, node.node)
                else:
                    result.append((new_prefix, node.node, active_type))
    return result


def semantic_analyze_target(target: str,
                            state: 'State',
                            node: Union[MypyFile, FuncDef],
                            active_type: Optional[TypeInfo]) -> List[str]:
    # TODO: Support refreshing function targets (currently only works for module top levels)
    tree = state.tree
    assert tree is not None
    analyzer = state.manager.new_semantic_analyzer
    # TODO: Move initialization to somewhere else
    analyzer.global_decls = [set()]
    analyzer.nonlocal_decls = [set()]
    analyzer.globals = tree.names
    with analyzer.file_context(file_node=tree,
                               fnam=tree.path,
                               options=state.options,
                               active_type=active_type):
        analyzer.refresh_partial(node, [])
    if analyzer.deferred:
        return [target]
    else:
        return []