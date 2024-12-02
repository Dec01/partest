import matplotlib.pyplot as plt

def create_chart(call_count):
    ''' Creating a graph that contains data on endpoint calls '''
    methods = []
    counts = []

    for (method, endpoint, description), count in call_count.items():
        methods.append(f"{description} ({method})")
        counts.append(count)

    plt.figure(figsize=(10, 6))
    plt.barh(methods, counts, color='skyblue')
    plt.xlabel('Количество вызовов')
    plt.title('Количество вызовов API по методам и описаниям')
    plt.tight_layout()

    # Сохранение графика в файл
    plt.savefig('api_call_counts.png')
    plt.close()