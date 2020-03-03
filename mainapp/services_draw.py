def get_field():
    points = [
        [150, 120],
        [800, 50],
        [1000, 600],
        [900, 700],
        [300, 750],
    ]
    return [coord for point in points for coord in point]
