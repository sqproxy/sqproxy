"""
https://gist.github.com/CMeza99/5eae3af0776bef32f945f34428669437
"""


def dict_merge(base_dct, merge_dct):
    """
    Recursive dict merge.
    Args:
        base_dct (dict) onto which the merge is executed
        merge_dct (dict): base_dct merged into base_dct
        add_keys (bool): whether to add new keys
    Returns:
        dict: updated dict
    """
    rtn_dct = base_dct.copy()
    rtn_dct.update(
        {
            key: dict_merge(rtn_dct[key], merge_dct[key])
            if isinstance(rtn_dct.get(key), dict) and isinstance(merge_dct[key], dict)
            else merge_dct[key]
            for key in merge_dct.keys()
        }
    )
    return rtn_dct
