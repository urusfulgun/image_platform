from fastapi import Request
from fastapi.responses import JSONResponse
from bff.service_layer.bff_proxy import BFFProxyService


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def bff_proxy_handler(
    path: str, request: Request, proxy: BFFProxyService = Depends(get_proxy_service)
):
    """
    Catch-all route that forwards frontend requests to the Gateway.
    """
    data, status_code = await proxy.forward_to_gateway(request, path)
    return JSONResponse(content=data, status_code=status_code)
