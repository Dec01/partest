import json

state1 = 'dev'
state2 = 'prod'

def compare_stands(file1, file2):
	with open(file1, 'r') as f1, open(file2, 'r') as f2:
		stats1 = json.load(f1)
		stats2 = json.load(f2)

	print(
		f"{'Endpoint':<20} {'Min (dev)':<10} {'Min (prod)':<10} {'Diff':<10} {'Avg (dev)':<10} {'Avg (prod)':<10} {'Diff':<10} {'Max (dev)':<10} {'Max (prod)':<10} {'Diff':<10}")
	print("-" * 100)

	for endpoint in set(stats1.keys()) | set(stats2.keys()):
		s1 = stats1.get(endpoint, {"min_time": 0, "max_time": 0, "avg_time": 0})
		s2 = stats2.get(endpoint, {"min_time": 0, "max_time": 0, "avg_time": 0})

		min_diff = s1["min_time"] - s2["min_time"]
		avg_diff = s1["avg_time"] - s2["avg_time"]
		max_diff = s1["max_time"] - s2["max_time"]

		print(
			f"{endpoint:<20} {s1['min_time']:<10.3f} {s2['min_time']:<10.3f} {min_diff:<10.3f} {s1['avg_time']:<10.3f} {s2['avg_time']:<10.3f} {avg_diff:<10.3f} {s1['max_time']:<10.3f} {s2['max_time']:<10.3f} {max_diff:<10.3f}")


if __name__ == "__main__":
	compare_stands("C:\\src\\aeroidea\\aerosite\\api_autotests\\response_times_dev.json", "C:\\src\\aeroidea\\aerosite\\api_autotests\\response_times_prod.json")