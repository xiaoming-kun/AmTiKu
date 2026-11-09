"""按业务域拆分的 FastAPI 路由。

`amti/web/server.py` 只负责 app 组装、中间件和跨域共享的运行时状态；
新路由优先放这里，不要再把业务往 4k 行的 server.py 里塞。
"""
