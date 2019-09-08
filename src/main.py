import torch
import torch.nn as nn
from torchvision import models
from pytorch_transformers import GPT2LMHeadModel
import logging
from loaders.vqa import *
from preprocessors.input import *

logging.basicConfig(level=logging.WARNING)


# This class represents, from a high level, a standard encoder decoder architecture
# In this project the encoder holds image and question encoded representations
# While the decoder acts as a conditioned generative model to produce answers
class EncoderDecoder(nn.Module):

    def __init__(self, encoder, decoder):
        super(EncoderDecoder, self).__init__()
        self.encoder = encoder
        self.decoder = decoder

    def forward(self, question, image):
        return self.decode(self.encode(question, image))

    def encode(self, question, image):
        return self.encoder(question, image)

    def decode(self, encoded):
        return self.decoder(encoded)


# This is a ResNet based encoder that uses a pre-trained resnet network
# We get rid of the last Linear layer originally trained to distribute probabilities
# over the 1000 classes of ImageNet on which it was trained.
# ----------------------------------------------------------------------------------
# For the moment the ResNet network is non-trainable and acts only as a feature extractor
class ImageEncoder(nn.Module):

    def __init__(self, out_size=768):
        super(ImageEncoder, self).__init__()
        # Using pre-trained ResNet
        self.resnet = models.resnet18(pretrained=True)

        # Disable dropout, prepare for feature extraction
        self.resnet.eval()

        # Disabling weight updates
        for param in self.resnet.parameters():
            param.requires_grad = False

        # Depending on the model, the last layer has different input sizes
        in_size = self.resnet.fc.in_features

        # Drop Last layer originally meant for ImageNet
        self.resnet.fc = nn.Linear(in_size, out_size)

    def forward(self, image):
        return self.encode(image)

    def encode(self, image):
        return self.resnet(image)


# This is the question encoder. It exploits the 774M parameters GPT-2 language model.
# We drop the last FC layer to get an encoded representation of the question.
# The pre-trained instance was distributing probabilities over the whole vocab (50k+ words)
class QuestionEncoder(nn.Module):
    def __init__(self, out_size=768, train_mode=True):
        super(QuestionEncoder, self).__init__()

        # Load pre-trained model (weights)
        self.gpt2 = GPT2LMHeadModel.from_pretrained('gpt2')

        # Set the model in evaluation mode to deactivate the DropOut modules
        # This is IMPORTANT to have reproducible results during evaluation!
        self.gpt2.eval() if not train_mode else self.gpt2.train()

        # Drop Last layer originally meant for softmax over vocabulary
        self.gpt2.lm_head = nn.Linear(768, out_size)

        # Put everything on cuda
        self.gpt2.to('cuda')

    def forward(self, question_tensor):
        # Get the gpt2 output
        return self.gpt2(question_tensor)


class Encoder(nn.Module):
    def __init__(self, size=768):
        super(Encoder, self).__init__()

        self.image_encoder = ImageEncoder(out_size=size)
        self.question_encoder = QuestionEncoder(out_size=size)

    def forward(self, question, image):
        # Pointwise multiplication between the two resulting tensors
        return torch.mul(self.question_encoder(question), self.image_encoder(image))


if __name__ == '__main__':

    loader = VQALoader()
    samples = loader.random_samples()
    q_in, i_in = prepare(samples)

