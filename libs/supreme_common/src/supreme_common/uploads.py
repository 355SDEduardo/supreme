from fastapi import HTTPException

async def read_upload(upload, limit):
    content = await upload.read(limit + 1)
    if not content or len(content) > limit:
        raise HTTPException(413, 'Arquivo vazio ou excede o limite de tamanho.')
    return content

class RequestLimitMiddleware:
    """Limit the actual body, including chunked transfers, before multipart parsing."""
    def __init__(self, app, limit=55 * 1024 * 1024):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        size, messages = 0, []
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > self.limit:
                return await JSONResponse({'detail': 'Requisição excede 55 MB.'}, 413)(scope, receive, send)
            messages.append(message)
            if not message.get('more_body'):
                break
        position = 0
        async def replay():
            nonlocal position
            if position < len(messages):
                message = messages[position]
                position += 1
                return message
            return await receive()
        await self.app(scope, replay, send)
