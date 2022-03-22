import os
from mpi4py import MPI
from mpi4py.futures import MPIPoolExecutor

import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt

import hoomd
import hoomd.md as md
import hoomd.dlext

import pysages
from pysages.collective_variables import Component
from pysages.methods import UmbrellaIntegration

param1 = {"A": 0.5, "w": 0.2, "p": 2}


def generate_context(**kwargs):
    """ Generate a simulation context to be used by the sampler
        - the initial configuration start.gsd was already generated
        - setting up time integrator, neighbor list
        - force field: dpd between all the particles
        - an external field on the tagged particle (tag 0, type A)
    """
    hoomd.context.initialize(mpi_comm=MPI.COMM_SELF)

    context = hoomd.context.SimulationContext()
    with context:
        print("Operating replica {0}".format(kwargs.get("replica_num")))
        system = hoomd.init.read_gsd("start.gsd")

        hoomd.md.integrate.nve(group=hoomd.group.all())
        hoomd.md.integrate.mode_standard(dt=0.01)

        nl = hoomd.md.nlist.cell()
        dpd = hoomd.md.pair.dpd(r_cut=1, nlist=nl, seed=42, kT=1.0)
        dpd.pair_coeff.set("A", "A", A=5.0, gamma=1.0)
        dpd.pair_coeff.set("A", "B", A=5.0, gamma=1.0)
        dpd.pair_coeff.set("B", "B", A=5.0, gamma=1.0)

        periodic = hoomd.md.external.periodic()
        periodic.force_coeff.set("A", A=param1["A"], i=0, w=param1["w"], p=param1["p"])
        periodic.force_coeff.set("B", A=0.0, i=0, w=0.02, p=1)
    return context


def plot_hist(result, bins=50):
    fig, ax = plt.subplots(2, 2)

    # ax.set_xlabel("CV")
    # ax.set_ylabel("p(CV)")

    counter = 0
    hist_per = len(result["centers"]) // 4 + 1
    for x in range(2):
        for y in range(2):
            for i in range(hist_per):
                if counter + i < len(result["centers"]):
                    center = np.asarray(result["centers"][counter + i])
                    histo, edges = result["histograms"][counter + i].get_histograms(bins=bins)
                    edges = np.asarray(edges)[0]
                    edges = (edges[1:] + edges[:-1]) / 2
                    ax[x, y].plot(edges, histo, label="center {0}".format(center))
                    ax[x, y].legend(loc="best", fontsize="xx-small")
                    ax[x, y].set_yscale("log")
            counter += hist_per
    while counter < len(result["centers"]):
        center = np.asarray(result["centers"][counter])
        histo, edges = result["histograms"][counter].get_histograms(bins=bins)
        edges = np.asarray(edges)[0]
        edges = (edges[1:] + edges[:-1]) / 2
        ax[1, 1].plot(edges, histo, label="center {0}".format(center))
        counter += 1

    fig.savefig("hist.pdf")


def external_field(r, A, p, w):
    return A * np.tanh(1 / (2 * np.pi * p * w) * np.cos(p * r))


def plot_energy(result):
    fig, ax = plt.subplots()

    ax.set_xlabel("CV")
    ax.set_ylabel("Free energy $[\epsilon]$")
    center = np.asarray(result["centers"])
    A = np.asarray(result["free_energy"])
    offset = np.min(A)
    ax.plot(center, A - offset, color="teal")

    x = np.linspace(-3, 3, 50)
    data = external_field(x, **param1)
    offset = np.min(data)
    ax.plot(x, data - offset, label="test")

    fig.savefig("energy.pdf")


def get_args(argv):
    parser = argparse.ArgumentParser(description="Example script to run umbrella integration")
    parser.add_argument(
        "--k-spring", "-k", type=float, default=50.0, help="spring constant for each replica"
    )
    parser.add_argument(
        "--N-replica", "-N", type=int, default=25, help="Number of replica along the path"
    )
    parser.add_argument(
        "--start-path", "-s", type=float, default=-1.5, help="Start point of the path"
    )
    parser.add_argument("--end-path", "-e", type=float, default=1.5, help="Start point of the path")
    parser.add_argument(
        "--time-steps",
        "-t",
        type=int,
        default=int(1e5),
        help="Number of simulation steps for each replica",
    )
    parser.add_argument(
        "--log-period",
        "-l",
        type=int,
        default=int(50),
        help="Frequency of logging the CVS for histogram",
    )
    parser.add_argument(
        "--discard-equi",
        "-d",
        type=int,
        default=int(1e4),
        help="Discard timesteps before logging for equilibration",
    )
    args = parser.parse_args(argv)
    return args


def main(argv):
    # parse the command line arguments
    args = get_args(argv)

    # define the collective variable: of type Component
    #   particle group: consisting particle of tag 0
    #   Cartesian coordinate axis component: 0 (X)
    cvs = [
        Component([0], 0),
    ]

    # create a list of centers for umbrella sampling of the CV(s)
    centers = list(np.linspace(args.start_path, args.end_path, args.N_replica))

    # define the sampling method with the CV, the CV centers and its specific parameters
    method = UmbrellaIntegration(cvs, centers, args.k_spring, args.log_period, args.discard_equi)

    # launch the sampling which returns the raw result:
    #   executor is responsible for launch multiple walkers each with ancontext
    preresult = pysages.run(method, generate_context, args.time_steps, executor=MPIPoolExecutor())

    # post-process the raw result: in this case analyze() is dispatched through UmbrellaIntegration
    result = pysages.analyze(preresult)

    # plotting the result
    plot_energy(result)
    plot_hist(result)


if __name__ == "__main__":
    main(sys.argv[1:])