from src.app.security.memory_rbac import get_rbac
rbac = get_rbac()
key = rbac.generate_api_key(owner_id="admin", name="load_test", roles=["admin"])
print(key["api_key"])
