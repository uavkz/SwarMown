def get_field_ga():
    """
    sorry for this poeben', peredelaem after generate_nodes()
    :return:
    """
    return [44, 27, 44, 43, 58, 44, 58, 27]


def generate_car_position():
    """
    # TODO replace in new implementation
    :return:
    """
    return [559, 411]


def generate_waypoints_ga(grid, drones_inits):
    import numpy as np

    if grid is None:
        grid = generate_nodes()
    print('!!! start calculations')
    generations = 57
    mutation_rate = 0.03
    population_size = 100
    elite_size = 20

    k_initial = 3  # default clusters num
    drone_base_fly_distance = 4500

    clusters, center_coordinates = generate_clusters(grid, k_initial)  # dict of clusters
    center = centeroid(center_coordinates)
    routes = list()
    total_distance = list()

    k_new = k_initial

    for cluster_id, cluster_points in clusters.items():
        nodes_list = [City(x=x, y=y) for x, y in cluster_points]
        d, route = geneticAlgorithm(nodes_list, population_size, elite_size, mutation_rate, generations)  # fix
        total_distance.append(d)
        k_new = np.sum(total_distance) // drone_base_fly_distance  # drone_base_fly_dist is a drone's maximum distance

    if total_distance:
        k_new += 1  # implement increase and decrease cluster num cases

    clusters_new, _ = generate_clusters(grid, int(k_new))
    total_distance = list()

    for cluster_id, cluster_points in clusters_new.items():
        nodes_list = [City(x=x, y=y) for x, y in [center] + cluster_points]
        distance, route = geneticAlgorithm(nodes_list, population_size, elite_size, mutation_rate, generations)
        if distance >= drone_base_fly_distance:
            k = (distance // drone_base_fly_distance + 1)
            k_new += k  # keep track of all clusters considering the new ones
            new_clusters, _ = generate_clusters(cluster_points, int(k))
            for c_new in new_clusters:
                nodes_list = [City(x=x, y=y) for x, y in [center] + c_new]
                distance, route = geneticAlgorithm(nodes_list, population_size, elite_size, mutation_rate, generations)
                assert distance < drone_base_fly_distance  # may not for complex clusters
                routes.append(route)
                total_distance.append(distance)
        else:
            routes.append(route)
            #         routes.append(route + [(route[0].x,route[0].y)])
            total_distance.append(distance)

    #     return [routes, total_distance]
    print('!!! calculations ended')
    final_list = []
    for drones_way in routes:
        drones_list = []
        for coords in drones_way:
            drones_list.append([coords.x, coords.y])
        final_list.append(drones_list)

    return final_list


def generate_nodes(**kwargs):
    """"""
    import matplotlib.pyplot as plt
    import matplotlib.patches
    import numpy as np

    el = matplotlib.patches.Ellipse((100, 100), 50, 50, 10, facecolor=(1, 0, 0, .2), edgecolor='none')

    y_int = np.arange(50, 200)
    x_int = np.arange(60, 140)

    g = np.meshgrid(x_int, y_int)
    coords = list(zip(*(c.flat for c in g)))

    ellipsepoints = np.vstack([p for p in coords if el.contains_point(p, radius=0)])

    # fig = plt.figure()
    # ax = fig.add_subplot(111)
    # ax.add_artist(el)
    # ax.plot(ellipsepoints[:, 0], ellipsepoints[:, 1], 'go')
    # plt.ylim(-31, -15)
    # plt.grid()
    # plt.show()

    return ellipsepoints


def generate_clusters(coordinates, n_clusters=5):
    from sklearn.cluster import KMeans
    from collections import defaultdict
    kmeans = KMeans(n_clusters=n_clusters, random_state=666)
    kmeans.fit(coordinates)
    labels = kmeans.labels_
    new_grids = defaultdict(list)
    for i, label in enumerate(labels):
        new_grids[label].append(list(coordinates[i]))

    return new_grids, kmeans.cluster_centers_


def plot_new_grids(new_grids):
    import matplotlib.pyplot as plt
    colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w']

    for key, value in new_grids.items():
        x_list, y_list = [], []

        for x, y in value:
            x_list.append(x)
            y_list.append(y)

        plt.grid()
        plt.plot(x_list, y_list, f'{colors[key]}o')

    return 'Done'


def centeroid(args):
    x_coords = [p[0] for p in args]
    y_coords = [p[1] for p in args]
    len_ = len(args)
    centeroid_x = sum(x_coords) / len_
    centeroid_y = sum(y_coords) / len_
    return [centeroid_x, centeroid_y]


class City:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def distance(self, city):
        import numpy as np

        xDis = abs(self.x - city.x)
        yDis = abs(self.y - city.y)
        distance = np.sqrt((xDis ** 2) + (yDis ** 2))
        return distance

    def __repr__(self):
        return "(" + str(self.x) + "," + str(self.y) + ")"


class Fitness:
    def __init__(self, route):
        self.route = route
        self.distance = 0
        self.fitness = 0.0

    def routeDistance(self):
        if self.distance == 0:
            pathDistance = 0
            for i in range(0, len(self.route)):
                fromCity = self.route[i]
                if i + 1 < len(self.route):
                    toCity = self.route[i + 1]
                else:
                    toCity = self.route[0]
                pathDistance += fromCity.distance(toCity)
            self.distance = pathDistance
        return self.distance

    def routeFitness(self):
        if self.fitness == 0:
            self.fitness = 1 / float(self.routeDistance())
        return self.fitness


def createRoute(cityList):
    import random

    route = random.sample(cityList, len(cityList))
    return route


def initialPopulation(popSize, cityList):
    population = []

    for i in range(0, popSize):
        population.append(createRoute(cityList))
    return population


def rankRoutes(population):
    import operator

    fitnessResults = dict()
    for i in range(0, len(population)):
        fitnessResults[i] = Fitness(population[i]).routeFitness()
    return sorted(fitnessResults.items(), key=operator.itemgetter(1), reverse=True)


def selection(popRanked, eliteSize):
    import pandas as pd
    import numpy as np
    import random

    selectionResults = []
    df = pd.DataFrame(np.array(popRanked), columns=["Index", "Fitness"])
    df['cum_sum'] = df.Fitness.cumsum()
    df['cum_perc'] = 100 * df.cum_sum / df.Fitness.sum()

    for i in range(0, eliteSize):
        selectionResults.append(popRanked[i][0])
    for i in range(0, len(popRanked) - eliteSize):
        pick = 100 * random.random()
        for i in range(0, len(popRanked)):
            if pick <= df.iat[i, 3]:
                selectionResults.append(popRanked[i][0])
                break
    return selectionResults


def breed(parent1, parent2):
    import random

    childP1 = list()

    geneA = int(random.random() * len(parent1))
    geneB = int(random.random() * len(parent1))

    startGene = min(geneA, geneB)
    endGene = max(geneA, geneB)

    for i in range(startGene, endGene):
        childP1.append(parent1[i])

    childP2 = [item for item in parent2 if item not in childP1]

    #     child = childP1 + childP2
    child = childP2[:startGene] + childP1 + childP2[startGene:]
    return child


def breedPopulation(matingpool, eliteSize):
    import random

    children = list()
    length = len(matingpool) - eliteSize
    pool = random.sample(matingpool, len(matingpool))

    for i in range(0, eliteSize):
        children.append(matingpool[i])

    for i in range(0, length):
        child = breed(pool[i], pool[len(matingpool) - i - 1])
        children.append(child)
    return children


def mutate(individual, mutationRate):
    import random
    
    for swapped in range(len(individual)):
        if random.random() < mutationRate:
            swapWith = int(random.random() * len(individual))

            city1 = individual[swapped]
            city2 = individual[swapWith]

            individual[swapped] = city2
            individual[swapWith] = city1
    return individual


def mutatePopulation(population, mutationRate):
    mutatedPop = []

    for ind in range(0, len(population)):
        mutatedInd = mutate(population[ind], mutationRate)
        mutatedPop.append(mutatedInd)
    return mutatedPop


def matingPool(population, selectionResults):
    matingpool = []
    for i in range(0, len(selectionResults)):
        index = selectionResults[i]
        matingpool.append(population[index])
    return matingpool


def nextGeneration(currentGen, eliteSize, mutationRate):
    popRanked = rankRoutes(currentGen)
    selectionResults = selection(popRanked, eliteSize)
    matingpool = matingPool(currentGen, selectionResults)
    children = breedPopulation(matingpool, eliteSize)
    nextGeneration = mutatePopulation(children, mutationRate)
    return nextGeneration


def geneticAlgorithm(population, popSize, eliteSize, mutationRate, generations):
    pop = initialPopulation(popSize, population)
    #     print("Initial distance: " + str(1 / rankRoutes(pop)[0][1]))

    for i in range(0, generations):
        pop = nextGeneration(pop, eliteSize, mutationRate)

    #     print("Final distance: " + str(1 / rankRoutes(pop)[0][1]))
    bestRouteIndex = rankRoutes(pop)[0][0]
    bestRoute = pop[bestRouteIndex]
    return 1 / rankRoutes(pop)[0][1], bestRoute


def geneticAlgorithmPlot(population, popSize, eliteSize, mutationRate, generations):
    import matplotlib.pyplot as plt
    pop = initialPopulation(popSize, population)
    progress = []
    progress.append(1 / rankRoutes(pop)[0][1])

    for i in range(0, generations):
        pop = nextGeneration(pop, eliteSize, mutationRate)
        progress.append(1 / rankRoutes(pop)[0][1])

    plt.plot(progress)
    plt.ylabel('Distance')
    plt.xlabel('Generation')
    plt.grid()
    plt.show()


def plot_routes(routes, center):
    import matplotlib.pyplot as plt
    colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'b', 'g', 'r', 'c', 'm', 'y', 'k']

    fig, ax = plt.subplots(figsize=(50, 30))

    for i in range(len(routes)):

        x = [point[0] for point in routes[i]]
        y = [point[1] for point in routes[i]]

        verts = list(zip(x, y))

        ax.plot(x, y, 'x--', lw=2, color=colors[i], ms=10, marker='o')

        for ind, (x, y) in enumerate(verts):
            ax.text(x, y, f'P{ind}', fontsize=30)
    plt.savefig('trajectory.png')

    return "Routes"
