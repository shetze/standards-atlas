# Can we use the Proven in Use Argument to travel between Safety Domains?

A Proven in Use argument is described under this name at least in IEC 61508 and ISO 26262. PiU opens up a way in which existing software (COTS) can be used as part of a system or as an element in a safety function for a safety case. The descriptions are specific to the domain and the use of PiU for the transfer of elements between different domains is not covered in the standard documents. Because the safety standards have a family relationship, such a journey may still be possible we would like to explore the topic further here.

Before such a journey can begin, it must be clarified from which starting point it should begin. Or more precisely: Is there a starting point at all? Can there be a proven-in-use argument for the use of Linux in a safety application in any domain?

# Is Linux mature and proven enough for use in safety-critical applications?

Linux has proven itself thousands, probably millions of times over in business-critical applications, so it may seem logical that we could use it for safety-critical applications as well. Linux has many advantages 

* it runs on an enormously wide range of hardware
* there are a large number of established vendors and service providers for the operating system and for additional (standard) software
* many specialists are familiar with it
* it is continuously being developed
* a large part of the innovation in IT is created on Linux and as open source software
* ...

Linux has obviously proven itself. So what is so difficult about safety-critical applications?

First, it's useful to look briefly at what functional safety is actually about. At its core, it is about potentially dangerous items: technical systems, devices, machines, vehicles and the like, which can harm the environment or people, and in the worst case can even kill people uninvolved in their operation.

For obvious reasons, the dangers posed by an item must be reduced to an acceptable level before the item is put into operation or placed on the market. 
Thus, to reduce the unavoidable risks from an item to an acceptable level, appropriate safeguards must be found and implemented at the design stage. These protective measures come into action under certain conditions and regulate the item in such a way that a previously identified and determined risk remains below a predetermined threshold. These protective measures are called safety functions. In certain situations, a safety function can put the item in a state recognized as safe, for example, by shutting the item down.

With the introduction of safety functions, the risk posed by an item now depends on the correct operation of that protective measure. Thus, the item is safe only to the extent that the safety function operates correctly and reliably even in the presence of faults within the item. This is the safety of the safety function, or simply functional safety.


Functional safety is the part of the overall safety of a system or piece of equipment that depends on automatic protection operating correctly in response to its inputs or failure in a predictable manner (fail-safe).

Functional safety is the part of the overall safety of a system that depends on automatic protection operating correctly in a predictable manner.

It is obvious to implement safety functions at least partially with electronic or programmable components. It is only in this context that the question of using Linux for safety-critical applications arises: as an operating system for a programmable component in one or more safety functions.

The Linux operating system is not an item. Therefore, it makes no sense to say Linux or any software is safe. Linux is a general-purpose operating system, it is not designed for any specific use case. For special use cases, Linux can be customized and configured both at compile time and at runtime.

As a component of a specific safety function, the instance of Linux that is individually configured and optimized for that use case must be functionally safe so that the safety function can reduce the danger posed by an item to an acceptable level. As a rule, specific real-time requirements are placed on the operating system for safety functions, among other things. For the mass of business-critical applications, for which Linux has proven itself so well in the past decades, such requirements are not made. This consideration alone gives a first indication that an analogy of applicability from mission-critical to safety-critical applications is not so simple.

As a component of a safety function, Linux becomes part of the safety architecture of a particular item. For the risk analysis of the item, the risk that the safety function does not intervene in time, does not intervene at all or intervenes incorrectly in some way must then also be systematically analyzed and evaluated for each safety function.

The systematic analysis and evaluation of risks is, at its core, a job that involves a lot of statistics and probability calculation. Probability theory is one of those mathematical disciplines where intuition and "common sense" often fail. This is the simple answer to the question of why Linux is not so easily a component for safety functions, even though it has proven itself so well for mission-critical applications. The simple analogy from mission-critical to safety-critical is intuitively obvious, but mathematically incorrect.

A more accurate answer requires somewhat deeper considerations.
The risk analysis for a technical system and its safety architecture is necessarily application-specific. Linux itself is only part of the safety function. In the specific mathematical consideration, a possible error of Linux in the safety function enters into a probability calculation. It is recognized and admitted that components can be used in a safety function which have proven themselves in other (as similar as possible) applications. Realistically, however, it must not simply be assumed that such a component is absolutely safe, i.e. that it functions correctly with probability 1.

An exact value for the intuitively obvious reliability of Linux is difficult to determine because of the complexity of the monolithic kernel. In order to arrive at a reasonably accurate value for the purpose with a defined small uncertainty, a lot of testing has to be done, and probability calculation is again used.

The mathematical details of the analysis established in IEC 61508 for proven in use are very well described, for example, at Exida and shall not be repeated in detail here. This way is possible, but unfortunately no longer intuitive. In IEC 61508 probabilistic limits are set for the SIL, which must be met for approval. For SIL 4, it is required that a dangerous failure occurs for a safety function with a high or continuous demand rate with an average frequency of less than 10-⁸/h (Probability of Dangerous Failure per Hour, PFHD). This means that proof must be provided that this safety function fails on average only every 11416 years. The limits from IEC 61508 for the PFHD have also been adopted in EN 50129 for the Tolerable Hazard Rate (THR). In ISO 26262-8 14.4.5.2.4, even 10-⁹/h is required for ASIL-D as the limit for the average frequency of actually observable malfunctions. For ASIL-B and ASIL-C, the limit of 10-⁸/h is set without difference.

This is a somewhat more detailed answer to the question of why Linux is not so easily suitable as a component for safety functions, even though it has proven itself so well for mission-critical applications.

The engineering consideration of functional safety has a history that goes back well beyond the existence of IEC 61508, ISO 26262 and EN 50128. Because the standards and norms that existed prior to 2001 did not adequately address the specifics of complex programmable electronic systems, IEC 61508 was written and published as a basic safety standard with a perspective strength for plant and process engineering. Following the publication of IEC 61508, the automotive industry developed its own standard tailored to its specific circumstances and requirements, which was first published in 2009 as ISO 26262. EN 50128 on software for railroad control and monitoring systems was first published in 2001.

Passive and active electronic safety systems for road vehicles were developed and launched long before ISO 26262. Airbag (1981), ABS (1978) and ESP (1995) have considerably increased the safety of automobiles and significantly contributed to the prevention of traffic fatalities even without the standard requirements of ISO 26262.

In order to be able to use such existing safety systems with the current standards, ISO 26262 in particular provides relatively detailed instructions compared with IEC 61508 and EN 50128 on how such safety systems, which have proven themselves in practice, can be approved under the new standard. In this context, the above-mentioned limits for the average frequency of actually observable malfunctions (10-⁹/h for ASIL-D, 10-⁸/h for ASIL-B and ASIL-C) are set as a prerequisite for compliance with the standard.

A derivation leading to all the above limits (PFHD, THR, ...) is not provided in all the documents. The only reference is that the risk posed by an item must be reduced to an acceptable level. How this acceptable level is to be determined is not further explained. The concrete figures apparently reflect a value held at discretion for the assumed social consensus. From a societal point of view, there is nothing to be said against high safety measures for dangerous items. However, the concrete figures also have an (economic) political significance. ISO-26262 is not legally required for the registration of road vehicles (in Germany). Vehicles that do not comply with this standard can be imported and put into operation quite legally. This means that risk-taking or unscrupulous entrepreneurs, as well as manufacturers with the backing of sufficiently determined governments, are free to put vehicles without the high safety standards into operation even in Germany (Europe, the USA). With regard to the approval of Linux as an operating system for safety functions, it may be appropriate to question the established limits and to discuss realistic requirements politically as well.

Compared to nuclear power plants or chemical plants, for example, unit numbers for safety systems in the automotive industry are comparatively high. In addition, the automobile manufacturers have a comprehensive and reliable database for their vehicles with fixed inspection intervals via the contract workshops, on which a mathematical proof of operational reliability can be provided. Therefore, it is not completely impossible for the automotive industry to provide this proof. However, this requires field data to be collected and evaluated over several years.

> ToDo: Insert details about the PiU procedure in the automotive industry

For open source software in general and Linux in particular, there is a database in the respective bug tracking systems, which can partly be seen as analogous to the workshop data of the automobile manufacturers. From these sources, however, the number of bug-free running systems and their uptime cannot be determined. Nor do they systematically record the details of the overall configuration of each individual system. However, all of these data are needed for the statistical analysis of functional safety.

It is obvious and must nevertheless be clearly repeated: Linux can never be approved 'as a whole' and 'in general' for use in safety-critical applications. There are any number of examples of Linux configurations and constellations in which the operating system fails mercilessly. Therefore, according to the conservative interpretation of the standard documents, only individual, fully specified systems can prove themselves. In this sense, every Linux system is unique and a PiU argument is categorically ruled out. 

In order to approach the PiU argumentation for Linux, the dimension of the system under consideration or the elements under consideration must be reduced and focused on the one hand. On the other hand, value ranges for configuration and constellation must be described that are recognized as equivalent with regard to the safety-critical application. If it is possible to document the elements in focus in running systems with their behavior, especially in the event of system errors and in extreme situations, and to document robust behavior, a PiU argumentation could be based on this.

In order to underpin the advantages of Linux with the large open source communities for a proof of operational reliability in the context of functional safety with the necessary field data, a sufficiently large number of users would have to be prepared to regularly supply "inspection data" of their Linux servers to an analysis system, for example at the Linux Foundation. On the basis of such data, it could then be possible in principle to provide the proven in use argument for certain components and subsystems of the Linux operating system.


Because Linux cannot be certified generally but always only for a concrete set of defined safety functions in each case, it is meaningful and necessary to conduct a proven in use argument for the configuration (compile and runtime) corresponding in each case to the application.

Linux is not a microkernel, but it is very largely modular. For the purpose of a PiU argument, the statistically considered configuration can possibly be reduced to an absolute minimum.

> ToDo: Consideration for decomposition and freedom from interference

In practice as well as for risk assessment, device drivers may be considered particularly problematic compared to the scheduler or mature file systems. These components should therefore perhaps be excluded from the PiU argument. The drivers required for a specific safety function must then be designed, developed and tested in accordance with the standards. 

In summary, it is not easy to derive suitability for safety-critical applications from the reliability of Linux as a server operating system. For such special use cases, high demands are placed on the evidence for error-free uptime. With the currently publicly available data, this proof cannot be provided with the currently required operating times. As a cooperative project of parties interested in functional safety for Linux, such an approach could perhaps be pursued further.

In any case, it is reasonable and necessary for some components of the Linux kernel to follow the path described in the norms and standards for developing functionally safe software. Overall, it may also be beneficial for other use cases to develop software according to functional safety criteria. The associated requirements for analysis, design, documentation, testing and management are costly. Because this is open source development, parties interested in functional safety for Linux can work cooperatively here as well.

ELISA provides a good framework for this collaboration.


## References and further information

* [Exida Determining Software Safety](https://www.exida.com/Resources/Whitepapers/determining-software-safety-understanding-the-possibilities-and-limitations)
* [Math behind PiU](https://ez.analog.com/ez-blogs/b/engineerzone-spotlight/posts/the-math-behind-proven-in-use)
* [Schlummer Beitrag zur Entwicklung einer alternativen Vorgehensweise für eine Proven-in-Use-Argumentation in der Automobilindustrie](https://d-nb.info/1022900226/34)

* IEC 61508-2:2010 7.4.2.2

  As a requirement for the E/E/PE system design and development, a general notion of a
  compliance Route 2S is introduced.
* IEC 61508-3:2010 7.4.2.12

  This requirement lists Route 2S as one way to achieve compliance.
  This bullet point is to be replaced with IEC 61508-3-1:2016 in a future version of IEC 61508-3
* IEC 61508-2:2010 7.4.10 :: Requirements for proven in use elements
* IEC 61508-4:2010 3.8.18 :: proven in use

  Here proven in use is defined as a means for confirmation of safety measures.
* IEC 61508-7:2010 C.2.10 :: Use of trusted/verified software elements

  The aim is to allow reuse of pre-existing software elements with confidence about the proper behaviour based on
  * operational history as described in
    IEC 61508-7:2010 C.2.10.1 :: Proven-in-use
  * qualification of software as described in
    IEC 61508-7:2010 C.2.10.2 :: Assess a body of verification evidence
* ISO 26262-1:2018 3.115 :: proven in use argument
* ISO 26262-1:2018 3.116 :: proven in use credit
* ISO 26262-8:2018 14 :: Proven in use argument
* ISO 26262-8:2018 14.4.2 :: Proven in use credit
* ISO 26262-8:2018 14.4.4.1 :: Proven in use candidates
* ISO 26262-8:2018 14.4.5.2 :: Target values for proven in use
* ISO 26262-8:2018 14.5.1 :: Description of candidate for proven in use argument
* ISO 26262-8:2018 14.5.2 :: Proven in use analysis report
* ISO 26262-10:2018 10 :: An example of proven in use argument
* ISO 26262-10:2018 10.2 :: Iteam definition and definition of the proven in use candidate
* ISO 26262-10:2018 10.4 :: Target values for proven in use
