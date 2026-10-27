from map_builder import generate_best_map

if __name__ == "__main__":
    for scenario in [8, 10, 25, 50, 100]:
        generate_best_map(scenario)
