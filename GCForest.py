import itertools
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_predict
from sklearn.metrics import accuracy_score


# noinspection PyUnboundLocalVariable
class gcForest(object):

    def __init__(self, n_mgsRFtree=30, window=[0],
                 n_cascadeRF=2, n_cascadeRFtree=101, min_samples=0.05):

        setattr(self, 'n_layer', 0)
        setattr(self, 'n_samples', 0)
        setattr(self, 'n_cascadeRF', int(n_cascadeRF))
        setattr(self, 'window', window)
        setattr(self, 'n_mgsRFtree', int(n_mgsRFtree))
        setattr(self, 'n_cascadeRFtree', int(n_cascadeRFtree))
        setattr(self, 'min_samples', min_samples)

    def fit(self, X, y, shape_1X):

        if np.shape(X)[0] != len(y):
            raise ValueError('Sizes of y and X do not match.')
        setattr(self, 'n_samples', np.shape(X)[0])
        setattr(self, 'shape_1X', shape_1X)
        mgs_X = self.mg_scanning(X, y)
        self.cascade_forest(mgs_X, y)

    def predict(self, X):

        mgs_X = self.mg_scanning(X)
        predictions = self.cascade_forest(mgs_X)

        return predictions

    def mg_scanning(self, X, y=None):

        shape_1X = getattr(self, 'shape_1X')
        if len(shape_1X) < 2:
            raise ValueError('shape parameter must be a tuple')

        mgs_pred_prob = []

        for wdw_size in getattr(self, 'window'):
            wdw_pred_prob = self.window_slicing_pred_prob(X, wdw_size, shape_1X, y=y)
            mgs_pred_prob.append(wdw_pred_prob)

        return np.concatenate(mgs_pred_prob, axis=1)

    def window_slicing_pred_prob(self, X, window, shape_1X, y=None):

        n_tree = getattr(self, 'n_mgsRFtree')
        min_samples = getattr(self, 'min_samples')

        if shape_1X[1] > 1:
            print('Slicing Images...')
            sliced_X, sliced_y = self._window_slicing_img(X, window, shape_1X, y=y)
        else:
            print('Slicing Sequence...')
            sliced_X, sliced_y = self._window_slicing_sequence(X, window, shape_1X, y=y)

        if y is not None:
            prf = RandomForestClassifier(n_estimators=n_tree, max_features='sqrt',
                                         min_samples_split=min_samples)
            crf = RandomForestClassifier(n_estimators=n_tree, max_features=None,
                                         min_samples_split=min_samples)
            print('Training Random Forests...')
            prf.fit(sliced_X, sliced_y)
            crf.fit(sliced_X, sliced_y)
            setattr(self, '_mgsprf', prf)
            setattr(self, '_mgscrf', crf)

        if hasattr(self, '_mgsprf') and y is None:
            prf = getattr(self, '_mgsprf')
            crf = getattr(self, '_mgscrf')

        pred_prob_prf = prf.predict_proba(sliced_X)
        pred_prob_crf = crf.predict_proba(sliced_X)
        pred_prob = np.c_[pred_prob_prf, pred_prob_crf]

        return pred_prob.reshape([getattr(self, 'n_samples'), -1])

    def _window_slicing_img(self, X, window, shape_1X, y=None):

        if any(s < window for s in shape_1X):
            raise ValueError('window must be smaller than both dimensions for an image')

        sliced_imgs = []
        sliced_target = []
        refs = np.arange(0, window * shape_1X[1], shape_1X[0])

        iterx = list(range(shape_1X[0] - window + 1))
        itery = list(range(shape_1X[1] - window + 1))

        for img, ix, iy in itertools.product(enumerate(X), iterx, itery):
            rind = refs + ix + shape_1X[0] * iy
            sliced_imgs.append(np.ravel([img[1][i:i + window] for i in rind]))
            if y is not None:
                sliced_target.append(y[img[0]])

        return np.asarray(sliced_imgs), np.asarray(sliced_target)

    def _window_slicing_sequence(self, X, window, shape_1X, y=None):

        if shape_1X[0] < window:
            raise ValueError('window must be smaller than the sequence dimension')

        sliced_sqce = []
        sliced_target = []

        for sqce in enumerate(X):
            slice_sqce = [sqce[1][i:i + window] for i in np.arange(shape_1X[0] - window + 1)]
            sliced_sqce.append(slice_sqce)
            if y is not None:
            sliced_target.append(np.repeat(y[sqce[0]], shape_1X[0] - window + 1))

        return np.reshape(sliced_sqce, [-1, window]), np.ravel(sliced_target)

    def cascade_forest(self, X, y=None, max_layers=5, tol=0.01):

        if y is not None:
            self.n_layer += 1
            prf_crf_pred = self._cascade_layer(X, y)
            _, accuracy_ref = self._layer_pred_acc(prf_crf_pred, y)
            feat_arr = self._create_feat_arr(X, prf_crf_pred)
            self.n_layer += 1
            prf_crf_pred = self._cascade_layer(X, y)
            layer_pred, accuracy_layer = self._layer_pred_acc(prf_crf_pred, y)
            feat_arr = self._create_feat_arr(X, prf_crf_pred)
            while (accuracy_ref * (1.0 + tol)) < accuracy_layer and self.n_layer <= max_layers:
                self.n_layer += 1
                prf_crf_pred = self._cascade_layer(feat_arr, y)
                layer_pred, accuracy_layer = self._layer_pred_acc(prf_crf_pred, y)
                feat_arr = self._create_feat_arr(X, prf_crf_pred)


        elif y is None:
            at_layer = 1
            prf_crf_pred = self._cascade_layer(X, layer=at_layer)
            layer_pred = self._layer_pred_acc(prf_crf_pred)
            feat_arr = self._create_feat_arr(X, prf_crf_pred)
            while at_layer <= getattr(self, 'n_layer'):
                at_layer += 1
                prf_crf_pred = self._cascade_layer(feat_arr, layer=at_layer)
                layer_pred = self._layer_pred_acc(prf_crf_pred)
                feat_arr = self._create_feat_arr(X, prf_crf_pred)

        return layer_pred

    def _cascade_layer(self, X, y=None, cv=3, min_samples=0.1, layer=0):

        n_tree = getattr(self, 'n_cascadeRFtree')
        n_cascadeRF = getattr(self, 'n_cascadeRF')

        prf = RandomForestClassifier(n_estimators=n_tree, max_features='sqrt',
                                     min_samples_split=min_samples)
        crf = RandomForestClassifier(n_estimators=n_tree, max_features=None,
                                     min_samples_split=min_samples)

        prf_crf_pred, crf_pred = [], []
        if y is not None:
            print('Adding/Training Layer, n_layer={}'.format(self.n_layer))
            for irf in range(n_cascadeRF):
                prf.fit(X, y)
                crf.fit(X, y)
                setattr(self, '_casprf{}_{}'.format(self.n_layer, irf), prf)
                setattr(self, '_cascrf{}_{}'.format(self.n_layer, irf), crf)
                prf_crf_pred.append(cross_val_predict(prf, X, y, cv=cv, method='predict_proba'))
                prf_crf_pred.append(cross_val_predict(crf, X, y, cv=cv, method='predict_proba'))
        elif y is None and hasattr(self, '_cascprf'.format(layer, 0)):
            for irf in range(n_cascadeRF):
                prf = getattr(self, '_casprf{}_{}'.format(layer, irf))
                crf = getattr(self, '_cascrf{}_{}'.format(layer, irf))
                prf_crf_pred.append(prf.predict_proba(X))
                prf_crf_pred.append(crf.predict_proba(X))

        return prf_crf_pred

    def _create_feat_arr(self, X, prf_crf_pred):

        swap_pred = np.swapaxes(prf_crf_pred, 0, 1)
        add_feat = swap_pred.reshape([getattr(self, 'n_samples'), -1])

        return np.concatenate([add_feat, X], axis=1)

    def _layer_pred_acc(self, prf_crf_pred, y=None):

        layer_pred_prob = np.mean(prf_crf_pred, axis=0)
        layer_pred = np.argmax(layer_pred_prob, axis=1)
        if y is not None:
            accuracy = accuracy_score(y_true=y, y_pred=layer_pred)
            print('Layer accuracy : {}'.format(accuracy))
            return layer_pred, accuracy
        elif y is None:
            return layer_pred
