import requests
import warnings
import threading
import numpy as np
import pandas as pd
import datetime as dt


warnings.simplefilter(action='ignore', category=DeprecationWarning)


results = []


class Death():
	def __init__(self, timestamp, player_name, inventory):
		self.player_name = player_name
		self.timestamp = timestamp
		self.inventory = inventory

	def get_info(self):
		return self.timestamp, self.player_name, self.inventory


class SuspectedRat():
	def __init__(self, player_name, timeout=5):
		self.threads = []
		self.timeframe = []
		self.player_name = player_name
		self.player_id = ''
		self.player_death_ids = []
		self.player_deaths = []
		self.timeout = timeout


	def item_id_to_item_name(self, item_id):
		try:
			item_name = requests.get(url=f'https://gameinfo.albiononline.com/api/gameinfo/items/{item_id}/data', timeout=self.timeout).json()['localizedNames']['EN-US']
			return item_name
		except Exception:
			pass


	def get_player_id(self):
		try:
			self.player_id = requests.get(url=f'https://gameinfo.albiononline.com/api/gameinfo/search?q={self.player_name}', timeout=self.timeout).json()['players'][0]['Id']
		except Exception:
			pass


	def get_player_deaths(self):
		try:
			player_deaths_temp = requests.get(url=f'https://gameinfo.albiononline.com/api/gameinfo/players/{self.player_id}/deaths', timeout=self.timeout).json()

			for death in player_deaths_temp:
				self.player_death_ids.append(death['EventId'])

		except Exception:
			pass


	def parse_player_death(self, death_id):
		try:
			inventory = []
			player_death = requests.get(url=f'https://gameinfo.albiononline.com/api/gameinfo/events/{death_id}', timeout=self.timeout).json()
			inventory_temp = player_death['Victim']['Inventory']
			timestamp = player_death['TimeStamp']

			for item in inventory_temp:
				if item:
					if '@' in item['Type']:
						inventory.append([self.item_id_to_item_name(item['Type']), int(item['Type'].split('@')[1]), int(item['Count'])])
					else:
						inventory.append([self.item_id_to_item_name(item['Type']), 0, int(item['Count'])])
			if inventory:
				self.player_deaths.append(Death(timestamp.split('Z')[0], self.player_name, inventory))
		except Exception:
			pass


	def parse_player_deaths(self):
		self.get_player_id()
		self.get_player_deaths()

		for death_id in self.player_death_ids:
			self.threads.append(threading.Thread(target=self.parse_player_death, args=(death_id,)))

		for thread in self.threads:
			thread.start()

		for thread in self.threads:
			thread.join()


	def player_deaths_to_df(self, index):
		global results
		player_deaths_list = []

		self.parse_player_deaths()

		for death in self.player_deaths:
			info = death.get_info()
			for item in info[2]:
				player_deaths_list.append([pd.to_datetime(info[0]), info[1], item[0], item[1], item[2]])

		player_deaths_df = pd.DataFrame(player_deaths_list, columns=['Date', 'Player Name', 'Item Name', 'Enchantment', 'Amount'])
		player_deaths_df.sort_values(by='Date')

		if not player_deaths_df.empty:
			results[index] = player_deaths_df


class Logs():
	def __init__(self, loot_log_path, chest_log_path, filter_list, timeout=5):
		self.loot_log_path = loot_log_path
		self.chest_log_path = chest_log_path
		self.missing_loot = None
		self.lost_loot = None
		self.filter_list = filter_list
		self.timeout = timeout

		self.tiers = ['Beginner', 'Novice', 'Journeyman', 'Adept', 'Expert', 'Master', 'Grandmaster', 'Elder']
		self.invalid_items = ['Rune', 'Soul', 'Relic', 'Bag', 'Cape', 'Demolition', 'Journal', 'Horse', 'Ox', 'Crest']

		self.loot_log = pd.read_excel(self.loot_log_path)
		self.chest_log = pd.read_excel(self.chest_log_path)


	# FILTER BY ALLIANCE NAMES OR GUILD NAMES
	def filter_allies(self, df, guild_or_alliance):
		if guild_or_alliance.lower() == 'a':
			return df.loc[df['Alliance'].isin(self.filter_list)]
		else:
			return df.loc[df['Guild'].isin(self.filter_list)]
			

	# FILTER OUT ALL ROWS WHERE SOME1 REMOVED AN ITEM FROM THE CHEST
	def filter_removes(self, df):
		index_names = df[df['Amount'] < 0].index
		df.drop(index_names, inplace=True)
		return df


	# FILTER OUT ALL ITEMS BUT GEAR
	def filter_armor(self, df):
		return_df = pd.DataFrame()

		for tier in self.tiers:
			return_df = pd.concat([return_df, df[df['Item Name'].str.contains(tier, na=False)]])

		for item in self.invalid_items:
			index_names = return_df[return_df['Item Name'].str.contains(item, na=False)].index
			return_df.drop(index_names, inplace=True)
			
		return return_df


	# LAMBDA FUNCTIONS
	# CLEAN STRING OF LOOT LOG
	def clean_item_name(self, string_to_clean):
		return_string = string_to_clean.split(' - ')
		return return_string[1]


	def clean_loot_log(self, guild_or_alliance):
		self.loot_log.columns = ['IDK', 'Date', 'Alliance', 'Guild', 'Player Name', 'Item Id', 'Item Name', 'Enchantment', 'Amount', 'Victim']
		self.loot_log.drop(['IDK', 'Item Id', 'Victim'], axis=1, inplace=True)
		self.loot_log = self.filter_allies(self.loot_log, guild_or_alliance)
		self.loot_log.drop(['Alliance', 'Guild'], axis=1, inplace=True)
		self.loot_log = self.filter_armor(self.loot_log)
		self.loot_log['Item Name'] = self.loot_log['Item Name'].apply(self.clean_item_name)
		self.loot_log['Date'] = pd.to_datetime(self.loot_log['Date'])
		self.loot_log = self.loot_log.sort_values(by='Date')
		self.loot_log = self.loot_log.reset_index(drop=True)


	def clean_chest_log(self, guild_or_alliance):
		self.chest_log.columns = ['Date', 'Player Name', 'Item Name', 'Enchantment', 'Quality', 'Amount']
		self.chest_log.drop(['Quality'], axis=1, inplace=True)
		self.chest_log = self.filter_removes(self.chest_log)
		self.chest_log = self.filter_armor(self.chest_log)
		self.chest_log['Date'] = pd.to_datetime(self.chest_log['Date'])
		self.chest_log = self.chest_log.sort_values(by='Date')
		self.chest_log = self.chest_log.reset_index(drop=True)


	def get_missing_loot(self, guild_or_alliance):
		self.clean_loot_log(guild_or_alliance)
		self.clean_chest_log(guild_or_alliance)

		relevant_chest_log_start = self.chest_log[self.chest_log['Date'] > self.loot_log['Date'].values[0]] 
		relevant_chest_log_end = self.chest_log[self.chest_log['Date'] < (self.loot_log['Date'].values[-1] + np.timedelta64(2, 'h'))]

		relevant_chest_log = relevant_chest_log_start.merge(relevant_chest_log_end, how='inner')

		keys = list(['Player Name', 'Item Name'])

		df1 = self.loot_log.set_index(keys).index
		df2 = relevant_chest_log.set_index(keys).index
		self.missing_loot = self.loot_log[~df1.isin(df2)]

		return self.missing_loot


	def get_lost_loot(self, guild_or_alliance):	
		global results
		threads = []
		all_players = []

		missing_loot = self.get_missing_loot(guild_or_alliance)
		all_player_names = missing_loot['Player Name'].values
		
		[all_players.append(x) for x in all_player_names if x not in all_players] 

		for i, player_name in enumerate(all_players):
			results.append(None)
			threads.append(threading.Thread(target=SuspectedRat(player_name, self.timeout).player_deaths_to_df(i)))

		for thread in threads:
			thread.start()

		for thread in threads:
			thread.join()

		for i, result in enumerate(results):
			try:
				if result.empty:
					results.pop(i)
			except Exception:
				results.pop(i)

		if results:
			lost_loot_log = pd.concat(results)
			lost_loot_log = self.filter_armor(lost_loot_log)
			lost_loot_log = lost_loot_log.reset_index(drop=True)

			self.lost_loot = lost_loot_log
			return self.lost_loot

	
	def compare_missing_loot_and_player_deaths(self, guild_or_alliance):
		lost_loot_df = self.get_lost_loot(guild_or_alliance)
		missing_loot_df = self.missing_loot

		if not lost_loot_df.empty:
			relevant_lost_loot_df_start = lost_loot_df[lost_loot_df['Date'] > missing_loot_df['Date'].values[0]]
			relevant_lost_loot_df_end = lost_loot_df[lost_loot_df['Date'] < (missing_loot_df['Date'].values[-1] + np.timedelta64(2, 'h'))]

			df = relevant_lost_loot_df_start.merge(relevant_lost_loot_df_end, how='inner')

			df1 = missing_loot_df.loc[missing_loot_df['Player Name'].isin(df['Player Name'].values)]
			df2 = missing_loot_df.loc[missing_loot_df['Item Name'].isin(df['Item Name'].values)]

			df = df1.merge(df2, how='inner')
			ratted_loot = pd.concat([missing_loot_df, df]).drop_duplicates(keep=False)

			return ratted_loot
		else:
			return missing_loot_df
	

	def generate_excel(self, output_file_name, guild_or_alliance):
		ratted_loot_log = self.compare_missing_loot_and_player_deaths(guild_or_alliance)

		writer = pd.ExcelWriter(output_file_name)
		self.loot_log.to_excel(writer, sheet_name='clean_loot_log')
		self.chest_log.to_excel(writer, sheet_name='clean_chest_log')
		ratted_loot_log.to_excel(writer, sheet_name='missing_loot')
		writer.save()


def main():
	filter_list = []
	alliance_list = ''
	guild_list = ''

	loot_log_path = input('[*] Enter path to loot log: ')
	chest_log_path = input('[*] Enter path to chest log: ')
	output_file_name = input('[*] Enter name of output file (default = output.xlsx): ')

	guild_or_alliance = input('[*] Would you like to filter by guilds or alliances? (g, a): ')

	if guild_or_alliance.lower() == 'a':
		alliance_list = input('[*] What alliances had to donate loot? (default = SURF): ')

		if alliance_list == '':
			filter_list = ['SURF']
		else:
			filter_list = alliance_list.split(',')

	else:
		guild_list = input('[*] What guilds had to donate loot? (default = Tidal): ')

		if guild_list == '':
			filter_list = ['Tidal']
		else:
			filter_list = guild_list.split(',')

	timeout = input('[*] Set timeout for albion servers (default = 5): ')

	if timeout == '':
		timeout = 5
	else:
		timeout = int(timeout)
	if output_file_name == '':
		output_file_name = 'output.xlsx'

	print('[*] Generating sheet of possible rats......')

	Logs(loot_log_path, chest_log_path, filter_list, timeout).generate_excel(output_file_name, guild_or_alliance)

	print(f'[*] Done! Wrote to: {output_file_name}')
main()
