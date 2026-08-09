_rpc_mod = None


def add_constraint(request):
    return _rpc_mod().invoke(request)
