from typing import List


class TreeType:
    pass


class TreeFactory:
    def __init__(self):
        self.tree_types: List[TreeType] = []

    def get_tree_type(self):
        tree_type = TreeType()
        self.tree_types.append(tree_type)
        return tree_type
