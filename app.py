import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import Choice

import os
import json
import aiohttp

import logging
from logging.handlers import TimedRotatingFileHandler

import dotenv
import python_aternos


dotenv.load_dotenv()

fP = os.path.dirname(os.path.realpath(__file__))
sP = os.path.dirname(os.path.realpath(__file__)) + "/sessions/{username}.aternos"
if not 'logs' in os.listdir(fP): os.mkdir(f"{fP}/logs")
if not 'sessions' in os.listdir(fP): os.mkdir(f"{fP}/sessions")
if not 'uconfig.json' in os.listdir(fP):
	with open('uconfig.json', 'w') as f:
		json.dump({"guilds": {}, "users": {}}, f, indent=2)

# Silence other loggers
#for log_name, log_obj in logging.Logger.manager.loggerDict.items():
#	if log_name == "discord.client":
#		log_obj.setLevel(logging.ERROR)
#	
#	elif log_name not in [__name__, "discord"]:
#		log_obj.disabled = True

logging.basicConfig(
	format='%(asctime)s %(levelname)-8s %(message)s',
	level=logging.DEBUG,
	datefmt='%Y-%m-%d %H:%M:%S'
)
handler = TimedRotatingFileHandler(f"{fP}/logs/acs.log", when="midnight", interval=1)
handler.suffix = "%Y%m%d"
formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
handler.setFormatter(formatter)
logger = logging.getLogger(__name__)
logger.addHandler(handler)


intents = discord.Intents.default()

bot = commands.Bot(
	command_prefix=commands.when_mentioned_or('aternos!'),
	description="Obtain your Aternos servers status and control them!",
	intents=intents
)
slash = bot.tree
bot.is_ready = False

@bot.event
async def on_ready():
	if not bot.is_ready:
		bot.is_ready = True
		logger.info("%s Logged in as %s#%s %s", '<'*15, bot.user.name, bot.user.discriminator, '>'*15)



def get_config():
	with open(f'{fP}/uconfig.json', 'r', encoding='utf-8') as f:
		c = json.load(f)

	return c

def save_config(cfg):
	with open(f'{fP}/uconfig.json', 'w', encoding='utf-8') as f:
		json.dump(cfg, f, ensure_ascii=False, indent=2)


def update_user(user_id, username: str=None, servers: list=None):
	config = get_config()
	u = config['users'].get(str(user_id))

	if u:
		username = username or u.get('username')
		servers = servers or u.get('servers')

	user = {
		"username": username,
		"servers": servers or []
	}
	config['users'][user_id] = user

	save_config(config)


@bot.command()
async def sync(ctx):
	if not str(ctx.message.author.id) == os.getenv('BOT_ADMIN'):
		return

	await bot.tree.sync()
	await ctx.message.add_reaction('✅')

@bot.command()
async def showdb(ctx):
	if not str(ctx.message.author.id) == os.getenv('BOT_ADMIN'):
		return

	await ctx.message.reply(file=discord.File(f"{fP}/uconfig.json"))



@slash.command()
async def informations(interaction: discord.Interaction):
	msg = """
	This bot does NOT save your credentials informations, but only your session settings, generated from the credentials you gave us.
	We do not sell or use your data for anything more than providing this bot.

	When you login to your Aternos account in a server, you allow EVERY member of the latter to start/stop & check status of your servers but only you will be able to perform elevated actions.
	You will need to login to your account in all the servers you want your Aternos servers be made available (*might change*)
	"""

	await interaction.response.send_message(msg, ephemeral=True)


@slash.command(description="Login with your Aternos account in order to use this bot.")
@app_commands.describe(
	username="Your Aternos username",
	password="Your Aternos password, or its md5 hash"
)
async def login(interaction: discord.Interaction, username: str, password: str):
	gid = str(interaction.guild.id)
	uid = str(interaction.user.id)

	await interaction.response.defer(ephemeral=True)

	# Let's check that credentials are valid
	try:
		aclient = python_aternos.Client.from_credentials(username, password)
	except python_aternos.CredentialsError:
		await interaction.followup.send(
			"Looks like your username and/or password is invalid. Please check and retry",
			ephemeral=True
		)
		return

	config = get_config()
	if not config['guilds'].get(gid):
		config['guilds'][gid] = {"logged_users": []}
	config['guilds'][gid]['logged_users'].append(uid)

	save_config(config)
	update_user(uid, username=username, servers=[s.domain for s in aclient.list_servers()])


	# Nice, let's save session settings for further interactions
	aclient.save_session(file=sP.format(username=username))
	

	await interaction.followup.send("✅ Successfully logged in!")


@slash.command(description="List servers available on this guild.")
async def list(interaction: discord.Interaction):
	gid = str(interaction.guild.id)
	uid = str(interaction.user.id)

	await interaction.response.defer(ephemeral=True)

	msg_e = discord.Embed(title="List of all Aternos servers available", description="")

	config = get_config()
	if config['guilds'].get(gid):
		for user in config['guilds'][gid]['logged_users']:
			cfg_user = config['users'].get(str(user))
			if cfg_user:
				msg_e.description += f"\n\nFrom <@{user}> ({cfg_user['username']}):"

				auser = python_aternos.Client.restore_session(file=sP.format(username=cfg_user['username']))
				update_user(user, servers=[s.domain for s in auser.list_servers()])


				for server in auser.list_servers():
					msg_e.description += f"\n\t- `{server.address}`, {server.version}"

	else:
		msg_e = discord.Embed(
			title="❌ There's no available Aternos server in this guild!",
			description="Start by login in using /login command",
			color=0xFF0000
		)


	await interaction.followup.send(embed=msg_e, ephemeral=False)


@slash.command(description="Set the default server address for your guild.")
@app_commands.describe(
	server_ip="The address of the server to set default."
)
async def setdefault(interaction: discord.Interaction, server_ip: str):
	gid = str(interaction.guild.id)
	uid = str(interaction.user.id)

	config = get_config()

	if not config['guilds'].get(gid):
		config['guilds'][gid] = {"logged_users": []}
	config['guilds'][gid]['default'] = server_ip

	save_config(config)

	await interaction.response.send_message(
		f"✅ Done! `{server_ip}` is now set as your guild default Minecraft server!",
		ephemeral=False
	)



@slash.command(description="Get any server status")
@app_commands.describe(
	private="Set to True if you don't want everyone to know you checked this server status.",
	server_ip="The address of the server you wanna check"
)
async def status(interaction: discord.Interaction, server_ip: str="default", port: int=46390, private: bool=False):
	gid = str(interaction.guild.id)
	uid = str(interaction.user.id)


	if server_ip == "default":
		config = get_config()
		guild = config['guilds'].get(gid)
		if guild:
			server_ip = guild.get('default')
			if not server_ip:
				await interaction.response.send_message(
					"❌ This guild does NOT have any default server ip configured.. Use /setdefault to do so.",
					ephemeral=False
				)
				return
		else:

			await interaction.response.send_message(
				"❌ This guild does NOT have any default server ip configured.. Use /setdefault to do so.",
				ephemeral=False
			)
			return

	await interaction.response.defer(ephemeral=private)


	async with aiohttp.ClientSession() as s:
		async with s.get("https://mcapi.us/server/status", params={"ip": server_ip, "port": port}) as r:
			res = json.loads(await r.text())

			if res['status'] != "success":
				msg = f"❌ There was an error.\n> {res['error']}"

				if res['last_updated'] + 60*5 > time.time():
					msg += "\n\n*/!\\ Be aware that the results are from less than 5 minutes ago, and thus might not be up to date!*"

			else:
				if res['players']['max'] == 0:
					if "Server not found" in res['motd']:
						msg = "❌ This aternos server was not found."
					elif "This server is offline" in res['motd']:
						msg = "❌ This aternos server is offline."

				else:
					if not res['online']:
						msg = "❌ This server is offline"

					else:
						# Get server name, cleaned
						sname = ''
						for i, char in enumerate(res['motd']):
							if char == "§" or res['motd'][max(0,i-1)] == "§":
								continue

							sname += char

						msg = f"✅ **{sname}** is online!"
						if res['players']['now'] > 0:
							if res['players']['max'] == res['players']['now']:
								msg += f"\n\nUnfortunately, the maximum number of {res['players']['max']} players has been reached.."
							else:
								msg += f"\n\nJoin the {res['players']['now']} current player{'s' if res['players']['now'] > 1 else ''}!"
								msg += f"\n> ip: `{server_ip}`\n> version: `{res['server']['name']}`"


	await interaction.followup.send(msg, ephemeral=private)


@slash.command(description="Turn on your Aternos servers")
@app_commands.describe(
	private="Set to True if you don't want everyone to know you turned on this server.",
	server_ip="The address of the server you wanna turn on"
)
async def turnon(interaction: discord.Interaction, server_ip: str="default", private: bool=False):
	gid = str(interaction.guild.id)
	uid = str(interaction.user.id)


	if server_ip == "default":
		config = get_config()
		guild = config['guilds'].get(gid)
		if guild:
			server_ip = guild.get('default')
			if not server_ip:
				await interaction.response.send_message(
					"❌ This guild does NOT have any default server ip configured.. Use /setdefault to do so.",
					ephemeral=False
				)
				return
		else:
			await interaction.response.send_message(
				"❌ This guild does NOT have any default server ip configured.. Use /setdefault to do so.",
				ephemeral=False
			)
			return


	await interaction.response.defer(ephemeral=private)

	config = get_config()
	for user in config['guilds'][gid]['logged_users']:
		if server_ip in config['users'][user]['servers']:
			aclient = python_aternos.Client.restore_session(file=sP.format(username=config['users'][user]['username']))

			servers = aclient.list_servers()
			for server in servers:
				if server.address == server_ip or server.domain == server_ip:
					try:
						server.start()
						msg = "✅ Server was successfully started! It should be up in 1 to 2 minutes."
					except Exception as e:
						msg = f"❌ An error occured.\n> {e}"


					await interaction.followup.send(msg, ephemeral=private)
					return

	await interaction.followup.send("❌ No user logged in have this server. Ask the Aternos server owner to /login")


@slash.command(description="Turn off your Aternos servers")
@app_commands.describe(
	private="Set to True if you don't want everyone to know you turned off this server.",
	server_ip="The address of the server you wanna turn off"
)
async def turnoff(interaction: discord.Interaction, server_ip: str="default", private: bool=False):
	gid = str(interaction.guild.id)
	uid = str(interaction.user.id)


	if server_ip == "default":
		config = get_config()
		guild = config['guilds'].get(gid)
		if guild:
			server_ip = guild.get('default')
			if not server_ip:
				await interaction.response.send_message(
					"❌ This guild does NOT have any default server ip configured.. Use /setdefault to do so.",
					ephemeral=False
				)
				return
		else:
			await interaction.response.send_message(
				"❌ This guild does NOT have any default server ip configured.. Use /setdefault to do so.",
				ephemeral=False
			)
			return


	await interaction.response.defer(ephemeral=private)

	config = get_config()
	for user in config['guilds'][gid]['logged_users']:
		if server_ip in config['users'][user]['servers']:
			aclient = python_aternos.Client.restore_session(file=sP.format(username=config['users'][user]['username']))

			servers = aclient.list_servers()
			for server in servers:
				if server.address == server_ip or server.domain == server_ip:
					try:
						server.start()
						msg = "✅ Server was successfully stopped!"
					except Exception as e:
						msg = f"❌ An error occured.\n> {e}"


					await interaction.followup.send(msg, ephemeral=private)
					return

	await interaction.followup.send("❌ No user logged in have this server. Ask the Aternos server owner to /login")



bot.run(os.getenv('DISCORD_BOT_TOKEN'))