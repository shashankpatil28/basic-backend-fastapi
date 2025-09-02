import asyncio, asyncpg, ssl

async def test():
    ssl_context = ssl.create_default_context()
    conn = await asyncpg.connect(
        user="neondb_owner",
        password="npg_rXMseISfY8k7",
        database="neondb",
        host="ep-floral-sunset-addtzcd1-pooler.c-2.us-east-1.aws.neon.tech",
        ssl=ssl_context
    )
    print("Connected OK!")
    await conn.close()

asyncio.run(test())
