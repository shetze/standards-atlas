# Motivation

The [Standards Atlas](https://github.com/shetze/standards-atlas) enables orientation and collaborative travel in the high-walled world of international norms and standards.

Standards and norms serve an important purpose in our modern industrial societies. It is about safety, about interoperability, about a baseline for the state of the art. In the field of programmable electronics and software, it has often proven useful to add concrete reference implementations to the textual standard documents. Such implementations facilitate dissemination, understanding, and serve as practical proof of interoperability. The use of open source methodology for the development of such reference implementations has also proven successful.

Unfortunately, most standards documents themselves are not freely available. Access to such documents, limited to an elite willing to pay, gives the impression of a medieval craft guild trying to protect its ruling knowledge. Such paywalls very fundamentally exclude all open source communities. This is perhaps one reason why there is so little active support from these communities for functional safety in open source software in general and Linux in particular.

The Standards Atlas cannot easily solve the problem, but it does open a path towards a solution.

This project provides a very comprehensive framework that can be used to span the scope of an entire family of valid standards. The outline of valid standards such as IEC 61608, ISO 26262, EN 50126 and EN 50657 can be found. The productive space of these standards is spanned by the open source requirement management tool [doorstop](https://github.com/doorstop-dev/doorstop). This makes it possible to work directly with the standards.

The framework of the standard documents allows to make connections to the clauses and between the clauses, and to integrate the standards into the concrete discussion about functional safety and into any projects with their specific requirements.

With doorstop, it is also very easy to add your own additions, annotations, and references to the existing standard framework. For example, depending on the needs and availability, the literal citations of the standard clauses that are missing in the framework due to copyright can be easily added via CSV import.

However, the real value of the standard atlas is that the structures with their links, notes and references can be freely exchanged and collaboratively used without the forbidden text parts. Reading the standards is one thing, using them in context is quite another. In this way, it may be possible to bring energizing open source spirit to functional safety work.
