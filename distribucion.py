import csv

with open("clima_historico.csv", newline="") as f:
    reader = csv.reader(f)
    next(reader)
    conditions = {}
    for line in reader:
        condition =line[12]
        if condition in conditions:
            conditions[condition] += 1
        else:
            conditions[condition] = 1
    
 
    for condition, count in conditions.items():
        print(f"{condition}: {count}")

grouped_conditions = {
    'Soleado': 0,
    'Nublado': 0,
    'Niebla': 0,
    'Lluvia': 0
}

for condition, count in conditions.items():
    cond = condition.lower()

    if "sunny" in cond or "clear" in cond:
        grouped_conditions['Soleado'] += count

    elif "cloud" in cond or "overcast" in cond:
        grouped_conditions['Nublado'] += count

    elif "fog" in cond or "mist" in cond:
        grouped_conditions['Niebla'] += count


    elif "rain" in cond or "drizzle" in cond or "thunder" in cond:
        grouped_conditions['Lluvia'] += count

print("\nCondiciones Agrupadas:")
for k, v in grouped_conditions.items():
    print(f"{k}: {v}")