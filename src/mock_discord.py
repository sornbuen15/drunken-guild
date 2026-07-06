import asyncio
import sys

sys.path.append("/Users/r.jakkawan/Projects/drunken-team/src")

from service.discord_router import DiscordRouter
from service.discord_runner import AgentRunner
from service.discord_utils import load_config


class MockUser:
    def __init__(self):
        self.name = "Boss"
        self.mention = "@Boss"
        self.bot = False
        self.id = 123456


class MockClient:
    def __init__(self):
        self.user = MockUser()
        self.user.name = "AgyBot"
        self.user.bot = True
        self.user.id = 999999


class MockChannel:
    def __init__(self, channel_id):
        self.id = channel_id

    async def send(self, content=None, file=None):
        print(f"\n[MockChannel.send] -> {content}")


class MockMessage:
    def __init__(self, content, channel_id):
        self.content = content
        self.author = MockUser()
        self.channel = MockChannel(channel_id)
        self.reference = None


async def main():
    config = load_config()
    channel_id = config.get("channel_id", "0")
    print(f"Loaded config channel_id: {channel_id}")

    client = MockClient()
    runner = AgentRunner()

    # We will override runner to just print what it would do
    async def mock_execute(*args, **kwargs):
        print(f"\n[MockAgentRunner] executing: {args}, {kwargs}")
        return 0, None

    runner._execute_command = mock_execute

    router = DiscordRouter(client, runner, channel_id)

    msg = MockMessage("!principal test discord message", channel_id)

    print("\n--- Sending message to router ---")
    await router.route(msg)

    # wait a bit for async tasks to run
    await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
