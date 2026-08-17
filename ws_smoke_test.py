import asyncio
import json

import httpx
import websockets

BASE = "http://localhost:8000"
WS = "ws://localhost:8000/ws"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as client:
        r = await client.post("/api/v1/auth/login", json={"email": "patient2@waterwatch.dev", "password": "Patient123!"})
        token = r.json()["data"]["access_token"]

        async with websockets.connect(f"{WS}?token={token}") as ws:
            print("WebSocket connected as patient2")

            async def listen():
                try:
                    async for message in ws:
                        data = json.loads(message)
                        print("WS EVENT:", data["type"], "-", data.get("data", {}))
                        if data["type"] == "NOTIFICATION":
                            return True
                except Exception as e:
                    print("listen error:", e)

            listener_task = asyncio.create_task(listen())
            await asyncio.sleep(1)

            # Trigger a fresh outbreak near patient2's location to generate a notification.
            r = await client.get("/api/v1/patient/me", headers={"Authorization": f"Bearer {token}"})
            profile = r.json()["data"]
            lat, lon = profile["latitude"], profile["longitude"]
            print(f"Simulating outbreak near patient2 at ({lat}, {lon})")

            r = await client.post(
                "/api/v1/dev/simulate-outbreak",
                json={
                    "disease": "TYPHOID",
                    "latitude": lat,
                    "longitude": lon,
                    "radius_km": 3,
                    "number_of_cases": 20,
                    "hours": 12,
                },
            )
            print("simulate-outbreak status:", r.status_code)

            try:
                await asyncio.wait_for(listener_task, timeout=10)
                print("\nWEBSOCKET REALTIME TEST PASSED")
            except asyncio.TimeoutError:
                print("\nWEBSOCKET REALTIME TEST: no NOTIFICATION event received within timeout")


if __name__ == "__main__":
    asyncio.run(main())
