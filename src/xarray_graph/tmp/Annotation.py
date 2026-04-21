""" Metadata for data/graph annotations.

Each annotation is represented as a simple dictionary with at least a 'type' and 'position' field.

The 'position' field contains a dictionary mapping dimension names to coordinate values defining a series of n-dimensional points which together with the 'type' field define the annotation's geometry.

For unnamed dimensions, 'position' may also be a list instead of a dict.

For example, a line/segment/arrow or rectangle/area/region annotation is defined by two n-dimensional points, while a polyline or polygon annotation is defined by a series of three or more n-dimensional points.

Other optional fields may include 'text' for annotation labels, 'style' for visual styling options, and 'group' for grouping related annotations.

Example annotations:
{
    'type': 'point',
    'position': {'time': 15, 'lat': 35, ...},
}
{
    'type': 'point',
    'position': [15, 35, ...],  # unnamed dimensions
}
{
    'type': 'arrow',
    'position': {'time': [10, 20], 'lat': [30, 40], ...},
    'text': 'some text\nwith multiple lines',
}
{
    'type': 'polyline',
    'position': {'time': [10, 20, 30, ...], 'lat': [30, 40, 50, ...], ...},
}
{
    'type': 'polyline',
    'position': [[10, 20, 30, ...], [30, 40, 50, ...], ...],  # unnamed dimensions
}
"""


def annotation_label(annotation: dict) -> str:
    """ Get a text label for an annotation.
    """
    # atype = annotation.get('type', '').lower()

    # label is the first line of the 'text' field if it exists
    text = annotation.get('text', '')
    label = text.strip(' ').split('\n')[0]
    if label != '':
        return label
    
    # label is a summary of the position data
    pos = annotation.get('position', None)
    if pos is None:
        return ''
    dim_labels: list[str] = []
    for dim, data in pos.items():
        data_labels: list[str] = [f'{val: .3g}'.strip() for val in data]
        if len(data_labels) > 3:
            data_labels = data_labels[:1] + ['...'] + data_labels[-1:]
        dim_label = f'{dim}: ({', '.join(data_labels)})'
        dim_labels.append(dim_label)
    label = ', '.join(dim_labels)
    return label
