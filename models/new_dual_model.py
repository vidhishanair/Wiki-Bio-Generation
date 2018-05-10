import torch
import torch.nn as nn
from models.decoder import Decoder
from models.encoder import Encoder
from torch.autograd import Variable
import math

from models.lstm_dual_attention_decoder import LSTMDualAttention


class Seq2SeqDualModel(nn.Module):
    def __init__(self, sent_vocab_size, field_vocab_size, ppos_vocab_size, pneg_vocab_size, value_vocab_size, sent_embed_size, field_embed_size, \
                 value_embed_size, ppos_embed_size, pneg_embed_size, encoder_hidden_size, decoder_hidden_size, decoder_num_layer, verbose, cuda_var, use_alignments):
        super(Seq2SeqDualModel, self).__init__()
        self.encoder_hidden_size = encoder_hidden_size
        self.sent_lookup = nn.Embedding(sent_vocab_size, sent_embed_size)
        self.field_lookup = nn.Embedding(field_vocab_size, field_embed_size)
        self.ppos_lookup = nn.Embedding(ppos_vocab_size, ppos_embed_size)
        self.pneg_lookup = nn.Embedding(pneg_vocab_size, pneg_embed_size)
        self.field_rep_embed_size = field_embed_size+ppos_embed_size+pneg_embed_size
        #self.decoder = nn.LSTM(input_size=sent_embed_size, hidden_size=encoder_hidden_size, num_layers=1, bidirectional=False, batch_first=True)
        self.encoder = nn.LSTM(input_size=sent_embed_size+self.field_rep_embed_size, hidden_size=decoder_hidden_size//2, num_layers=1, bidirectional=True, batch_first=True)
        self.decoder = LSTMDualAttention(input_size=sent_embed_size, field_rep_size=self.field_rep_embed_size, hidden_size=decoder_hidden_size, encoder_hidden_size=encoder_hidden_size, batch_first=True)
        self.linear_out = nn.Linear(encoder_hidden_size, sent_vocab_size)
        self.verbose = verbose
        self.use_alignments = use_alignments
        self.cuda_var = cuda_var
        self.init_weights()
        self.x = nn.Parameter(torch.zeros(1), requires_grad=True)

    def init_weights(self):
        torch.nn.init.xavier_uniform(self.sent_lookup.weight)
        torch.nn.init.xavier_uniform(self.field_lookup.weight)
        torch.nn.init.xavier_uniform(self.ppos_lookup.weight)
        torch.nn.init.xavier_uniform(self.pneg_lookup.weight)

    # def forward(self, sent, value, field, ppos, pneg, batch_size, value_mask):
    #     input_d = self.sent_lookup(value)
    #     input_z = torch.cat((self.field_lookup(field), self.ppos_lookup(ppos), self.pneg_lookup(pneg)), 2)
    #     input = torch.cat((input_d,input_z), 2)
    #     encoder_output, encoder_hidden = self.encoder(input, None)
    #     #encoder_hidden = None
    #     sent = self.sent_lookup(sent)
    #     decoder_output, decoder_hidden = self.decoder(sent, encoder_hidden)
    #     decoder_output = self.linear_out(decoder_output)
    #     return decoder_output, decoder_hidden


    def forward_with_attn(self, sent, value, field, ppos, pneg, batch_size, value_mask):

        input_d = self.sent_lookup(value)
        input_z = torch.cat((self.field_lookup(field), self.ppos_lookup(ppos), self.pneg_lookup(pneg)), 2)
        input = torch.cat((input_d,input_z), 2)
        encoder_output, encoder_hidden = self.encoder(input, None)
        #encoder_hidden = None
        sent = self.sent_lookup(sent)
        encoder_hidden = (encoder_hidden[0].view(1, encoder_hidden[0].size(1), encoder_hidden[0].size(0)*encoder_hidden[0].size(2)), encoder_hidden[1].view(1, encoder_hidden[1].size(1), encoder_hidden[1].size(0)*encoder_hidden[1].size(2)))
        encoder_hidden = (encoder_hidden[0].squeeze(0),encoder_hidden[1].squeeze(0))
        decoder_output, decoder_hidden, attn = self.decoder.forward(sent, encoder_hidden, input_z, encoder_output)
        decoder_output = self.linear_out(decoder_output)
        logsoftmax = nn.LogSoftmax(dim=2)
        decoder_output = logsoftmax(decoder_output)

        return decoder_output, decoder_hidden # should return the changed and weighted decoder output and not this output
        # should return decoder_output + LfAi + e

    def generate(self, value, value_len, field, ppos, pneg, batch_size, \
                 train, max_length, start_symbol, end_symbol, dictionary, unk_symbol, \
                 ununk_dictionary, value_ununk, value_mask, sent):
        input_d = self.sent_lookup(value)
        input_z = torch.cat((self.field_lookup(field), self.ppos_lookup(ppos), self.pneg_lookup(pneg)), 2)
        input = torch.cat((input_d,input_z), 2)
        encoder_output, encoder_hidden = self.encoder(input, None)
        gen_seq = []
        unk_rep_seq = []
        start_symbol =  Variable(torch.LongTensor(1,1).fill_(start_symbol))
        if self.cuda_var:
            start_symbol = start_symbol.cuda()
        curr_input = self.sent_lookup(start_symbol) # TODO: change here to look and handle batches
        # print curr_input.shape()
        prev_hidden =  (encoder_hidden[0].squeeze(0),encoder_hidden[1].squeeze(0))
        for i in range(max_length):
            # decoder_output, prev_hidden, attn_vector = model.decoder.forward_biased_lstm(input=curr_input, hidden=prev_hidden, encoder_hidden=encoder_output, input_z=input_z, mask=value_mask)
            decoder_output, prev_hidden, attn_vector = self.decoder.forward(curr_input, prev_hidden, input_z, encoder_output)
            decoder_output = self.linear_out(decoder_output)
            max_val, max_idx = torch.max(decoder_output.squeeze(), 0)
            curr_input = self.sent_lookup(max_idx).unsqueeze(0)
            # TODO: Issue here
            # print curr_input.shape()
            # exit(0)
            if dictionary.idx2word[int(max_idx)] == '<eos>':
                break
            if int(max_idx) == unk_symbol:
                if self.cuda_var:
                    value_ununk = value_ununk.cuda()
                unk_max_val, unk_max_idx = torch.max(attn_vector[0][0,:value_len[0]], 0)
                sub = value_ununk[0][unk_max_idx] # should be value_ununk
                word = ununk_dictionary.idx2word[int(sub)] # should be replaced from ununk dictionary word_ununk_vocab
                print("Unk got replaced with", word)
            else:
                word = dictionary.idx2word[int(max_idx)]
            gen_seq.append(dictionary.idx2word[int(max_idx)])
            unk_rep_seq.append(word)
            if dictionary.idx2word[int(max_idx)] == '<eos>':
                break
        return gen_seq, unk_rep_seq