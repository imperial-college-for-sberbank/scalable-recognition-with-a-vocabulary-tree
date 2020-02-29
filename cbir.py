import numpy as np
from sklearn.cluster import MiniBatchKMeans
import networkx as nx
import matplotlib.pyplot as plt
from dataset import Dataset
import time
import warnings
import multiprocessing


class CBIR(object):
    def __init__(self, root, n_branches, depth, sift_implementation="pytorch", initialise=False):
        self.dataset = Dataset(root, sift_implementation=sift_implementation)
        self.n_branches = n_branches
        self.depth = depth
        self.tree = {}
        self.nodes = {}

        # private:
        self._current_index = 0

        # init graph
        self.graph = nx.DiGraph()

        if initialise:
            # build the tree
            self.fit()

            # compute inverted index
            self.index()
        return

    def extract_features(self, image=None):
        if (image is not None):
            return self.dataset.extract_features(image)

        features = []
        times = []
        total = len(self.dataset.all_images)
        for i, path in enumerate(self.dataset.all_images):
            start = time.time()
            features.extend(self.dataset.extract_features(path))
            times.append(time.time() - start)
            avg = np.mean(times)
            eta = avg * total - avg * (i + 1)
            print("Extracting features %d/%d from image %s - ETA: %2fs" %
                  (i + 1, total, path, eta), end="\r")
        print("\n%d features extracted" % len(features))
        return np.array(features)

    def fit(self, features=None, node=0, root=None, current_depth=0):
        """
        Generates a hierarchical vocabulary tree representation of some input features
        using hierarchical k-means clustering.
        This function populates the graph and stores the value of the features in
        `self.nodes` as a dictionary Dict[int, numpy.ndarray] that stores the actual value for each node
        Args:
            features (numpy.ndarray): a two dimensional vector of input features where dim 0 is samples and dim 1 is features
            node (int): current node id to set
            root (numpy.ndarray): the value of the parent of the `node` as a virtual feature
            current_depth (int): the depth of the node as the distance in jumps from the very root of the tree
        """
        if features is None:
            features = self.extract_features()
        if root is None:
            root = np.mean(features)

        self.nodes[node] = root
        self.graph.add_node(node)

        # if `node` is a leaf node, return
        if current_depth >= self.depth or len(features) < self.n_branches:
            return

        # group features by cluster
        print("Computing clusters %d/%d with %d features from node %d at level %d\t\t" %
              (self._current_index, self.n_branches ** self.depth, len(features), node, current_depth), end="\r")
        model = MiniBatchKMeans(n_clusters=self.n_branches)
        model.fit(features)
        children = [[] for i in range(self.n_branches)]
        for i in range(len(features)):
            children[model.labels_[i]].append(features[i])

        # cluster children
        self.tree[node] = []
        for i in range(self.n_branches):
            self._current_index += 1
            self.tree[node].append(self._current_index)
            self.graph.add_edge(node, self._current_index)
            self.fit(children[i], self._current_index,
                     model.cluster_centers_[i], current_depth + 1)
        return

    def index(self, parallel=True):
        """
        Generates the inverted index structure using tf-idf.
        This function also calculates the weights for each node as entropy.
        """
        # create inverted index
        print("\nGenerating index")
        if parallel:
            pool = multiprocessing.Pool()
        times = []
        total = len(self.dataset.all_images)
        done = 0
        for i, image_path in enumerate(self.dataset.all_images):
            start = time.time()
            if parallel:
                pool.apply_async(self.propagate, (image_path,))
            else:
                self.propagate(image_path)
            times.append(time.time() - start)
            avg = np.mean(times)
            eta = avg * total - avg * (i + 1)
            done += 1
            print("Indexing image %d/%d:  %s - ETA: %2fs" %
                  (done + 1, total, image_path, eta), end="\r")

        # set weights of node based on entropy
        print("\nCalculating weights")
        N = len(self.dataset)
        for node_id, files in self.graph.nodes(data=True):
            N_i = len(files)
            if N_i:  # if the node is visited, calculate the weight, otherwise, leave it as initialised
                self.graph.nodes[node_id]["w"] = np.log(
                    N / N_i)  # calculate entropy
        print("Inverted index generated")
        return

    def propagate(self, image_path):
        """
        Proapgates the features of an image down the tree, until the find a leaf.
        Every time they pass through a node, they leave a fingerprint, by storing a key value pairm
        where the key is the id of the image and the value is the number of times that node is visited.
        This results into an tf-idf scheme.
        Args:
            image_path (str): path of the image to encode
        """
        features = self.extract_features(image_path)
        image_id = self.dataset.get_image_id(image_path)
        for feature in features:
            path = self.propagate_feature(feature)
            for i in range(len(path)):
                node = path[i]
                # add tfidf
                if image_id not in self.graph.nodes[node]:
                    self.graph.nodes[node][image_id] = 1
                else:
                    self.graph.nodes[node][image_id] += 1
        return

    def propagate_feature(self, feature, node=0):
        """
        Propagates a feature, down the tree, and returns the paths in the form of node ids.
        Args:
            feature (numpy.ndarray): The feature to lookup
            root (List[int]): Node id to start the search from.
                        Default is 0, meaning the very root of the tree
        """
        path = [node]
        while self.graph.out_degree(node):  # recur, stop if leaf
            min_dist = float("inf")
            for child in self.graph[node]:
                distance = np.linalg.norm(
                    [self.nodes[child] - feature])  # l1 norm
                if distance < min_dist:
                    min_dist = distance
                    node = child
                path.append(child)
        return path

    def encode(self, image_id, return_graph=True):
        if return_graph:
            subgraph = self.graph.subgraph(
                [k for k, v in self.graph.nodes(data=image_id, default=None) if v is not None])
            colours = ["C0"] * len(self.graph.nodes)
            for node in subgraph.nodes:
                colours[node] = "C3"
            self.draw(node_color=colours)
            return subgraph

        weights = np.array(self.graph.nodes(data="w", default=1))[:, 1]
        tfidf = np.array(self.graph.nodes(data=image_id, default=0))[:, 1]

        tfidf_normalised = tfidf / np.linalg.norm(tfidf, ord=1)  # l1 norm
        return tfidf_normalised  # * weights

    def score(self, first_image_path, second_image_path):
        """
        Measures the similatiries between the set of paths of the features of each image.
        """
        # get the vectors of the images
        db_id = self.dataset.get_image_id(first_image_path)
        query_id = self.dataset.get_image_id(second_image_path)
        d = self.encode(db_id, return_graph=False)
        q = self.encode(query_id, return_graph=False)

        # simplified scoring using the l2 norm
        score = 2 - 2 * np.sum(d * q)
        return score

    def retrieve(self, query_image_path, n=4):
        # propagate the query down the tree
        self.propagate(query_image_path)

        scores = {}
        for database_image_path in self.dataset.all_images:
            db_id = self.dataset.get_image_id(database_image_path)
            scores[db_id] = self.score(database_image_path, query_image_path)
        sorted_scores = {k: v for k, v in sorted(
            scores.items(), key=lambda item: item[1])}
        return sorted_scores

    def show_results(self, query_path, scores_dict, n=4):
        fig, ax = plt.subplots(1, n + 1, figsize=(20, 10))
        ax[0].axis("off")
        ax[0].imshow(self.dataset.read_image(query_path))
        ax[0].set_title("Query image")
        img_ids = list(scores_dict.keys())
        scores = list(scores_dict.values())
        for i in range(1, len(ax)):
            ax[i].axis("off")
            ax[i].imshow(self.dataset.read_image(f"C:\\Users\\epignatel\\Documents\\repos\\sberbank\\data\\jpg\\{img_ids[i - 1]}.jpg"))
            ax[i].set_title("#%d. %s Score:%.3f" %
                            (i, img_ids[i - 1], scores[i - 1]))
        return

    def draw(self, figsize=None, node_color=None, layout="tree"):
        figsize = (30, 10) if figsize is None else figsize
        plt.figure(figsize=figsize)
        layout = layout.lower()
        if "tree" in layout:
            layout = "dot"
        elif "radial" in layout:
            layout = 'twopi'
        pos = nx.drawing.nx_agraph.graphviz_layout(self.graph, prog=layout)
        nx.draw(self.graph, pos=pos, with_labels=True, node_color=node_color)
        return