import torch
import torch.nn as nn


class Encoder(nn.Module):
    def __init__(self, z_size, hidden_size, embed_size):
        super(Encoder, self).__init__()
        self.embed_size = embed_size
        self.hidden_size = hidden_size
        self.z_size = z_size
        # Weights W_*x
        self.input_weights = nn.Linear(embed_size, 4 * hidden_size)
        #self.weight_ix = Parameter(torch.Tensor(embed_size, hidden_size))
        #self.weight_ox = Parameter(torch.Tensor(embed_size, hidden_size))
        #self.weight_fx = Parameter(torch.Tensor(embed_size, hidden_size))
        #self.weight_ctildex = Parameter(torch.Tensor(embed_size, hidden_size))

        # Weights W_*h
        self.hidden_weights = nn.Linear(hidden_size, 4 * hidden_size)
        #self.weight_ih = Parameter(torch.Tensor(hidden_size, hidden_size))
        #self.weight_oh = Parameter(torch.Tensor(hidden_size, hidden_size))
        #self.weight_fh = Parameter(torch.Tensor(hidden_size, hidden_size))
        #self.weight_ctildeh = Parameter(torch.Tensor(hidden_size, hidden_size))

        # Weights z_t
        self.z_weights = nn.Linear(z_size, 2 * hidden_size)
        #self.weight_lx = Parameter(torch.Tensor(z_size, hidden_size))
        #self.weight_zhatx = Parameter(torch.Tensor(z_size, hidden_size))

    # Always batch first is needed
    def forward(self, input_d, input_z, hidden, cell_state): # input vector, h_0 intialized as 0's and same for cell state
        def recurrence(d_t, z_t, h_t_1, c_t_1):
            gates_vanilla = self.input_weights(d_t) + self.hidden_weights(h_t_1)
            ingate, forgetgate, cellgate, outgate = gates_vanilla.chunk(4, 1)
            gates_field = self.z_weights(z_t)
            lgate, zhatgate = gates_field.chunk(2, 1)

            ingate = F.sigmoid(ingate)
            forgetgate = F.sigmoid(forgetgate)
            cellgate = F.tanh(cellgate)
            outgate = F.sigmoid(outgate)
            lgate = F.sigmoid(lgate)
            zhatgate = F.tanh(zhatgate)

            c_t = (forgetgate * c_t_1) + (ingate * cellgate) + (lgate * zhatgate)
            h_t = outgate * F.tanh(c_t)

            return h_t, c_t

        output = []
        steps = range(input_d.size(1))  # input_d = batch X seq_length X dim
        for i in steps:
            hidden, cell_state = recurrence(input_d[:,i,:], input_z[:,i,:], hidden, cell_state)
            output.append((hidden, cell_state))  # output[t][1] = hidden = batch x hidden ;; same for cell_state
        #output = torch.cat(output, 0).view(input.size(0), *output[0].size())
        return output, hidden, cell_state
