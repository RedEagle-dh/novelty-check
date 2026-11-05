I want to tune a chat language model on pairs of answers where people marked which of the two
they prefer. The usual pipeline first fits a separate network that scores answers and then runs a
reinforcement-learning loop against that scorer, which is unstable and expensive. My idea: derive
a loss directly from the pairwise comparison model, so the language model itself can be trained
with a simple supervised, classification-style objective on the preference pairs. A frozen copy
of the starting model acts as an anchor so the tuned model does not drift too far from it.
